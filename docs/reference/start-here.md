# START HERE — AMAZON MONITORING SYSTEM



## WHAT THIS IS
- A set of AI agents that monitors the Amazon business on a fixed schedule and reports what needs attention.
- Each agent owns a defined set of metrics. No metric has two owners.
## THE PROBLEM IT SOLVES
- Monitoring today is manual: several dashboards, several reports, and a person remembering what to check and when.
- Any process that depends on someone remembering will eventually be missed, and nobody will notice it was missed.
## HOW THE SYSTEM IS BUILT
- **Domain agents** — Twelve agents. Each reads only the metrics it owns and returns a structured report: finding, no finding, or cannot answer. — run in parallel
- **LOOKER** — Starts the run, collects every report, validates it, removes duplicates, and assembles a single picture of the period. — no data access, no interpretation
- **SKAUT** — Reads that picture and the reports behind it, checks raw data and the knowledge base where needed, and produces recommendations, workflows and next actions. — the only agent with raw data access
- **Product managers** — Receive conclusions and actions, not a dump of metrics.
## WHY NARROW AGENTS RATHER THAN ONE GENERAL ONE
- An agent with a fixed scope and a fixed data source produces materially fewer wrong answers than one asked to cover everything.
- LOOKER has no access to raw data by design. It cannot state a number that no agent reported.
- SKAUT does have access, so a different control applies: every number it states must trace back to a metric and its source. Anything it adds beyond the agent findings is labelled as a hypothesis.
## ONE ROOT CAUSE, ONE REPORT
- A stockout appears simultaneously as falling sales, rising advertising cost, dropping keyword position, falling conversion and falling margin.
- That is one root cause with five symptoms. LOOKER collapses them using a fixed cause order and reports a single item with the rest attached underneath.
- Without that step a manager receives five alerts for one event, and stops trusting the report.
## HOW OFTEN EACH CHECK RUNS
- **Daily - alert** — Conditions requiring same-day action: out of stock, listing suppressed, Buy Box lost, account health warning, a product that sold yesterday and nothing today.
- **Daily** — Volume and inventory cover, observed rather than acted on.
- **Weekly** — The analytical layer: sales, advertising, conversion, keyword position, margin. Most decisions belong here. — daily analysis reacts to noise
- **Biweekly** — Product posture review - is this product growing, holding, or declining.
- **Quarterly** — Strategy assignment for each product.
- **When clean** — No findings means no report is sent.
## WHAT EACH TAB CONTAINS
- **Claude Monitoring Plan** — Every metric monitored - 95 in total - with its rule, its owner, its frequency and where it escalates. — the WHAT
- **Agent Orchestration** — The process contract: run sequence, agent scope, comparison periods, thresholds, cause order, report format, and the rules that prevent invented findings. — the HOW
- **Rules - SALES** — The diagnostic logic of the first agent: entry trigger, decomposition, check order, routing, and the decisions still open. — the first agent
## HOW TO READ THE MONITORING PLAN
- **AGENT / AREA** — The agent that owns every metric in the block below it. The sheet is grouped by agent.
- **WHAT IS CHECKED** — The thing being measured.
- **RULE / THRESHOLD** — The condition that makes it a finding, and the level at which it is normal.
- **AGENT CODE** — The same agent as the block header, repeated on every row so the sheet can be filtered and sorted.
- **CADENCE** — How often the check runs.
- **WHO GETS IT** — Where the finding is handed next - another agent when the cause belongs to them, or a person.
- **RULE SOURCE** — Where the rule came from. Titan is the Amazon seller network we follow: PLOG is their optimisation guide, PPC 3.0 their advertising framework, States+Drivers their prioritisation matrix. Blank means the rule is ours, not theirs.
- **METRIC ID** — The short code agents use to name this exact metric in a report, so every number traces back to one row of this sheet.
## TERMS USED IN THIS WORKBOOK
- **SKU / ASIN** — Identifiers for a single product. SKU is ours, ASIN is Amazon's.
- **Sessions** — Visits to the product page.
- **Unit session % / CVR** — Share of visits that resulted in a purchase. Organic uses unit session %, advertising uses CVR - they are not the same number.
- **CTR** — Share of impressions that resulted in a click.
- **BSR** — Best Sellers Rank - position within the category. Lower is better.
- **Buy Box** — The add-to-cart position on a listing. Losing it means another seller receives the order.
- **PPC** — Paid advertising on Amazon.
- **ACOS** — Advertising spend as a percentage of the revenue that advertising generated. — measured against breakeven
- **TACOS** — Advertising spend as a percentage of total revenue, paid and organic combined.
- **Organic** — Sales generated without advertising.
- **CM1 / CM2 / CM3** — Contribution margin after landed cost, after Amazon fees, and after advertising. — targets 70% / 35% / 20-25%
- **Days of cover** — Days of sales remaining at current velocity. — target band 45-90 days
- **Suppressed** — Amazon has removed the listing from search results. No notification is sent.
- **SQP** — Search Query Performance - Amazon's report of the search terms behind impressions, clicks and purchases. — lags 3-5 days
- **Stranded** — Inventory held at Amazon that cannot be sold.
## BUILD SEQUENCE
- **Phase 1** — Report format, cause order, LOOKER and SKAUT, and three domain agents: SALES, PPC, INVENTORY. — proves the contract
- **Phase 2** — FINANCE, then TRAFFIC, RANK and LISTING. — margin targets precede PPC targets
- **Phase 3** — PRICE, CUSTOMER, HEALTH, EXTERNAL, STRATEGY. — require new data sources first
- **Open decisions** — Seven rules require a team decision before the sales agent can be built. Listed at the bottom of Rules - SALES.
