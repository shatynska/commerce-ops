## Context

See `proposal.md` — Why. The constraints that shape the approach:

- Faults reach the surface as `InvalidPlaybookError.faults`, a tuple of
  plain strings.
- Faults come from **four** places: the domain's coherence rules, the
  application's write-time preconditions (roster and handler registry),
  the adapter's enum parsing in `_authorable_fields`, and the adapter's
  anchor parsing in `_anchor_from_form`.
- **The four sources do not meet.** `_authorable_fields` raises before
  `update_step` or `create_step` is called, so an adapter fault and a
  domain fault can never appear in one rejection. This bounds what the
  change can promise — see *What "every fault" can and cannot mean*.
- Only `save_edit` and `create` call `_authorable_fields` and
  `_anchor_from_form`. `retire`, `unretire`, `change_status` and `move`
  do not, and render their faults on `page.html`, which carries no
  authorable form.
- `_fields.html` is shared by the edit and create surfaces, so a marking
  mechanism written once serves both.
- `_fields.html` already carries two ways of saying "not offered" —
  `disabled` on the automation controls, `hidden` on the anchor groups —
  for reasons `add-step-page` recorded.
- The project is pure Python with no Node toolchain
  (`AGENTS.md` — Development Tooling).

Line numbers are omitted throughout: the previous draft of this change
carried a dozen and every one was stale by the time
`redesign-step-fields` landed.

## Goals / Non-Goals

**Goals:**

- Turn a fault list into something an admin can act on without
  translating prose back into controls.
- Keep the mapping's fragility both minimal and visible.
- Leave every fault rendered, always.

**Non-Goals:**

- Changing any rule, any fault's wording, or what a write accepts.
  `launch-playbook` and `playbook-authoring` are untouched.
- Attribution on the step list. Three of the five write routes reject
  onto `page.html`, which has no authorable form; those rejections keep
  rendering exactly as they do today.
- Client-side validation.
- The presentation of a marked field — colour, placement, iconography.
  `admin-presentation-vocabulary` owns that.

## Decisions

### Attribution is two-tier: structural where the field is known, mapped only where it is not

The original draft of this design proposed one text-keyed mapping over
all twenty-two attributable faults. That was wrong, and the correction
halves the risk the change accepts.

**Eleven faults already know their field at the point they are raised.**
`_enum(name, enum_type, fallback)` is *given* the input name. The create
route knows it is parsing the discipline. After the anchor restructure
below, the anchor parser knows which box it read. For these, attribution
is structural: the fault is raised carrying its fields, and no string is
ever matched. A reworded message cannot break them, because nothing
reads the message.

**Eleven faults arrive as prose from another layer** — the domain's
coherence rules and the application's preconditions. These cross a module
boundary as strings and cannot carry adapter field names, so these alone
are text-keyed.

The split matters because the text-keyed half is exactly the half where
the coupling is real. A domain rule reworded *is* a change the admin
surface should notice; an adapter fault reworded is a change inside one
file. Keying the second on text was accepting fragility for nothing.

**The two tiers can never appear in one rejection**, which is why no
ordering or merge rule is needed between them and why one rendering
shape suffices. Context records the fact for a different purpose: the
adapter's faults are raised before the write is called, and the
text-keyed faults come only from the write. The same fact makes the
identifier-stripping rule below simpler than it looks — only text-keyed
faults carry a `step '<identifier>' ` prefix at all, so classification
never has to reason about the structural half.

**The structural carrier SHALL make fields a required argument.** The
exemption claimed below — that the structural half cannot silently gain
an unattributed fault the way the text-keyed half can — holds only if a
new adapter fault cannot be raised without deciding its fields. A
carrier defaulting to none would reintroduce exactly the silent gap the
split removes, and mypy is what enforces it.

### Attribution lives in the adapter, not in the domain

The alternative — promoting faults to a structured
`Fault(fields=..., message=...)` in the domain so the rule that knows its
fields says so — is rejected, and the ground that carries it is the
first:

**Field names are adapter vocabulary.** The domain knows a step has a
`timing_anchor`; it does not know that a window anchor renders as two
numeric inputs named `anchor_start` and `anchor_end`, and it must not
learn. `Fault(fields=["anchor_start", "anchor_end"])` in
`launch_playbook.py` inverts the dependency direction the module
contract rests on.

A second consideration, weaker but real: `InvalidPlaybookError`'s shape
is shared with `access/domain/principals.py`, so changing it reaches a
bounded context with no stake in this. This is recorded as supporting,
not load-bearing — the first ground decides it alone.

**What the rejection costs, stated plainly:** eleven domain and
application faults are attributed by matching message text, so a
reworded rule silently stops matching and degrades to page level. The
requirement permits that degradation by design, so the rendering would
never reveal it. That is what the exhaustiveness requirement exists to
catch.

### What "every fault" can and cannot mean

`_authorable_fields` raises before the use case is called. So a
submission wrong in an enum **and** wrong in a domain rule reports only
the enum fault, and no change confined to the adapter can alter that —
the domain fault is never computed.

The strengthened guarantee in the editing requirement is therefore
scoped to **the values the surface itself parses**: enum faults, anchor
faults, and — on the create surface — the discipline arrive together,
where today the anchor's raise discards the enum faults gathered beside
it. That is a real defect with a two-line fix, and it is all this change
can honestly promise.

**The discipline has to move for that scope to be honest.** It is parsed
in the create route *after* `_authorable_fields` has already raised, so
a create wrong in an enum and in the discipline reports one fault today.
Leaving it there would make the rescoped promise true on the edit
surface and false on the create one, for a reason no reader could
recover — and the point of scoping the promise precisely was to state it
at the width it is actually honoured. It joins the same accumulator.

Widening it to all four sources would mean moving validation ordering
across the application boundary, which is a different change against a
different capability.

### The inventory

**Structurally attributed, adapter-raised (11):**

| Fault | Field(s) |
|---|---|
| unrecognised `scope` | `scope` |
| unrecognised `kind` | `kind` |
| unrecognised `status` | `status` |
| unrecognised `hazard` | `hazard` |
| unrecognised discipline (create route) | `discipline` |
| unparseable `anchor_days` | `anchor_days` |
| unparseable `anchor_start` | `anchor_start` |
| unparseable `anchor_end` | `anchor_end` |
| unrecognised cadence | `anchor_cadence` |
| unknown anchor kind | `anchor_kind` |
| window end precedes start | `anchor_start`, `anchor_end` |

**Text-keyed, crossing from domain or application (11):**

| Fault | Field(s) | Layer |
|---|---|---|
| declares unknown gate | `gate` | domain |
| has an empty name | `name` | domain |
| name spanning more than one line | `name` | domain |
| `prohibited-tactic` cannot block its gate | `hazard`, `blocking` | domain |
| automated, beyond draft, no automation brief | `kind`, `status`, `automation_brief` | domain |
| automated and active but names no handler | `kind`, `status`, `handler` | domain |
| human step cannot carry an automation brief | `kind`, `automation_brief` | domain |
| human step cannot name a handler | `kind`, `handler` | domain |
| names assignee the roster does not carry | `assignees` | application |
| active human step names no active assignee | `kind`, `status`, `assignees` | application |
| names handler no registered use case answers to | `handler` | application |

Eleven plus eleven is twenty-two. The seven combination faults span nine
distinct fields.

**Recognised, held at page level, provokable by a write (1):** a gate
left with no active blocking step. It concerns no control the form
carries, so it is not attributed — but it **is** classified, explicitly,
as set-level with no fields. Recognising it is what lets the
exhaustiveness check tell "held by the criterion" from "fell through
unmatched", and it is the only page-level fault an edit or a create can
reach.

**Not provokable by any authoring write, so outside the exhaustiveness
obligation (7):** the four faults `_gate_sequence_faults` produces —
unexpected gate, missing gate, wrong position, wrong opening mode —
plus `_gate_condition_faults`'s empty threshold description, since
`_validate` always constructs with `framework_gates()` and a write
cannot make the gate framework wrong; duplicate step identifier, since
identifiers are generated collision-free and cannot be updated; and
`StepDefinition.__post_init__`'s unrecognised discipline, which the
adapter's own `Discipline(...)` refuses first. Listed so the next reader
does not go looking for a way to provoke them.

**Rendered on the step list, not on an authoring form:**
`change_status`'s status parse fault and `reorder_step`'s two
`ValueError`s. Out of scope; see the non-goal.

### The anchor's parse failures have to be made attributable first

`_anchor_from_form` reads all three integer inputs inside one `try` and
re-raises as `timing anchor: {exc}` — `invalid literal for int() with
base 10: 'soon'`. **Which input failed is not in the message**, so this
is not a mapping problem: no entry can recover what the string does not
carry. The fix is to parse each input where its name is known.

Two constraints on that restructure, both load-bearing:

- **Keep reading only the inputs the submitted anchor kind uses.** The
  archived requirement *A timing anchor offers only the inputs its own
  kind uses* has not-offered inputs still submitting their values, so
  that a reconsidered kind discards nothing. Parsing eagerly would make
  a stale `soon` in a hidden Start box reject a write that succeeds
  today — a rule change this change forswears.
- **Keep every failure wrapped in `InvalidPlaybookError`.** `save_edit`
  catches only that type. A `WindowAnchor.__post_init__` `ValueError`
  escaping unwrapped turns a rendered fault into a 500.

### The dropped-faults path is adopted, not left beside the work

`_authorable_fields` accumulates enum faults, then assigns
`fields["timing_anchor"] = _anchor_from_form(form)` **before** reaching
`if faults: raise`. An anchor failure raises through the accumulator,
discarding every enum fault gathered.

Left alone, this change would attribute faults to fields on a path where
most of the faults never arrive. It is a small fix, in a function this
change already restructures, and the editing requirement's "every fault"
promise is already false because of it.

**Alternative rejected — a separate change.** It would mean shipping
attribution over a known hole, then writing a change whose only content
is two lines in a function this one just rewrote.

### Marking is a third axis, and applies to controls that are not offered

The partial already distinguishes `disabled` (automation controls on a
human step — the value must not reach the write) from `hidden` (anchor
groups the current kind does not use — the value must survive and still
submit). Marking is neither: it says a submitted value was refused.

**A marked control may be one of the not-offered ones**, and the
combination treatment guarantees it. A `human` step carrying an
automation brief marks both `kind` and `automation_brief` — and
`automation_brief` renders `disabled` in exactly that state. So marking
SHALL render the fault text adjacent to the control regardless of
whether the control is offered; what marking must never do is change
whether it is offered.

That case is worth understanding rather than designing away. The
actionable half of the pair is `kind` — and the fault self-clears if
resubmitted untouched, since a disabled control submits nothing. Marking
both is still right: it tells the admin *why* the pair is refused, which
is the difference between a form that explains itself and one that
silently drops a value.

### Stripping the generated identifier

A rejected create's faults name a step by an identifier `create_step`
generated before validating, which names nothing persisted.

The mechanism falls out of the attribution work: **the classification
already separates step-level faults from set-level ones**, because that
separation is what decides whether a fault marks a field. A step-level
fault reported by a create can only concern the step being created, and
this is spec-backed rather than inferred — `playbook-authoring`'s *Every write is
validated as the playbook it would produce* — its scenario *What a write
cannot persist, a load cannot see* — makes the persisted set coherent by
construction under every load-time rule, and that requirement's third
paragraph scopes the two precondition rules to the steps the write
touches, which for a create is the new definition alone.

So the leading `step '<identifier>' ` is removed and the rest of the
fault is left exactly as reported. The rule is stated in the delta so it
is assertable, rather than left to an implementer to invent prose the
change otherwise forbids.

**A fault the classification does not recognise keeps its identifier.**
Unrecognised means unclassified, and guessing would strip identifiers
from set-level faults that legitimately name other steps.

### The exhaustiveness requirement, and what it does not cover

A test provokes every rule a write can provoke and asserts each fault is
either attributed or is the **recognised** page-level entry. Asserting
against a recognised entry rather than against the criterion in the
abstract is what makes the criterion checkable: it separates "held
deliberately" from "fell through unmatched", which are otherwise one
state wearing two names.

Two limits, recorded rather than glossed:

- **"Deliberately page-level" is bound to a criterion, not to the
  mapping.** A fault is held at page level when it concerns no control
  the form carries — a property of the fault, checkable by a reader.
  Defining it as "whatever the mapping declines to attribute" would make
  the requirement vacuous, satisfiable by declaring every gap deliberate.
- **It catches a reworded rule, not a newly added one.** Nothing
  enumerates the rule set mechanically, so a rule added later is not
  caught until someone notices. A source-derived check — extracting
  format strings from the three modules and asserting the mapping's key
  set against them — would catch both, at the cost of coupling a test to
  source text. Not taken here; recorded so the next person can weigh it
  rather than rediscover the gap.

The structural half of the attribution is exempt from both limits, which
is the point of the two-tier split.

## Risks / Trade-offs

- **Eleven faults are keyed on message text.** → Accepted, mitigated by
  the exhaustiveness requirement, and half the exposure of the original
  design.
- **A fault reworded in the domain breaks a `playbook-admin` test.** →
  Intended. That is the coupling made visible.
- **The exhaustiveness test does not catch a newly added rule.** →
  Recorded above and in task 3.7. Deliberately not in the requirement:
  a spec states what must hold, and how far checking it reaches is a
  property of the verification.
- **This change rewrites `_authorable_fields` and `_anchor_from_form`.**
  → Consumed by `save_edit` and `create` only. There is no existing
  adapter test for `timing anchor:` or `not a recognised value`, so
  those tests are written here rather than relied on.
- **Marking ships unstyled.** → `admin-presentation-vocabulary` owns the
  vocabulary and is sequenced after this deliberately.

## Migration Plan

None. No schema, data or persisted-state change.

## Open Questions

- Whether a page-level fault should say *why* it is page-level — "this
  concerns the step set, not this form". Deferred: it is wording, it
  changes no requirement, and it belongs with the presentation change.
- Whether the step list should attribute the status parse fault to the
  row it concerns. Out of scope here; it needs a marking mechanism for a
  table rather than a form.
