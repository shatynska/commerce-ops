# External reference material

These four documents were **supplied to us**. They are not project-authored, and they are **not to be edited** — they are the record of what an external source says, and their value depends on that record staying faithful.

| File | What it is |
|---|---|
| `product-launch.md` | The Amazon product-launch plan: 358 identified items across ten thematic areas and twelve disciplines, each with a timing anchor, a FRAMEWORK/LESSON binding, and a citation |
| `monitoring.md` | The steady-state monitoring registry: metrics with their rule, cadence, owner and recipient |
| `agent-orchestration.md` | The process contract: run sequence, roster, comparison periods, cause order, report format |
| `start-here.md` | Overview of the monitoring system and how the other documents relate |

## How to use them

Treat them as **input, not schema**. They describe what work exists and why; they do not dictate how this project models or executes it. Two places where we knowingly diverge, both recorded with their justification in `openspec/changes/add-launch-playbook/design.md`:

- Their ten "areas" are thematic groupings, not an execution sequence. Our ordering spine is a sequence of commitment gates instead.
- `agent-orchestration.md` names six gates. We define eight — adding a gate for the purchase order, and splitting go-live from the marketing launch — on the strength of rows in `product-launch.md` itself.

Two known defects to be aware of when reading:

- The `OUR RULE / DECISION` column in `product-launch.md` is **empty on all 358 rows**. The source says what is taught, never what we do.
- `product-launch.md:3` describes all ten `TOS RISK` rows uniformly as "tactics … recognised and refused". The rows do not bear that out: four are tactics to refuse, four are compliance obligations that must be satisfied, and two are hazard warnings.

Our own identifiers never reuse theirs. Reference identifiers such as `lp.inventory.040` appear in our artifacts only as provenance citations.
