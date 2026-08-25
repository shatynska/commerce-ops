## Purpose

The admin surface's roster page: people are listed, created, edited, deactivated and reactivated from the browser, on the same authenticated admin surface the playbook page rides.

## ADDED Requirements

### Requirement: The roster page shows the roster whole

The admin surface SHALL serve a roster page listing every active person — display name, Slack identity, ClickUp user id, admin flag — on one page without pagination. Deactivated people SHALL be reachable from the page but visibly set apart from the active roster, never interleaved with it. Each entry's attribution SHALL be readable from the page — who created it and when, and its most recent update, deactivation or reactivation with who and when — this visibility being the audit that replaces the deleted directory file's git trail.

#### Scenario: An entry's attribution is readable

- **WHEN** an admin views a person's entry on the roster page
- **THEN** the page presents who created the entry and when, and the most recent change to it with who made it and when

#### Scenario: The whole active roster is one page

- **WHEN** an admin opens the roster page
- **THEN** every active person is listed on that one page with their identity data and admin flag

#### Scenario: Deactivated people are reachable but set apart

- **WHEN** the roster holds deactivated people
- **THEN** the page presents them distinctly from the active roster, and never mixed into it

### Requirement: A person can be created and edited from the page

The roster page SHALL offer creating a person and editing an existing person's updatable fields. A clean write SHALL land through the roster's write use cases and the page SHALL reflect it. A rejected write SHALL re-present the form with every reported fault and the submitted values still in place, and SHALL persist nothing.

#### Scenario: A created person appears on the page

- **WHEN** an admin submits a valid new person from the page
- **THEN** the person appears on the active roster with the submitted identity data

#### Scenario: A rejected write shows every fault with the typed values

- **WHEN** an admin submits a person the roster's validation rejects
- **THEN** the form is re-presented showing every fault and still holding the submitted values, and the roster is unchanged

### Requirement: Deactivation and reactivation are available from the page

The roster page SHALL offer deactivating an active person and reactivating a deactivated one. A refused deactivation — the last-admin refusal — SHALL be surfaced on the page with the refusal's explanation, leaving the roster unchanged.

#### Scenario: A deactivation lands and the person is set apart

- **WHEN** an admin deactivates a person who is not the last active admin
- **THEN** the person leaves the active roster and appears among the deactivated

#### Scenario: A blocked deactivation explains itself

- **WHEN** an admin attempts to deactivate the last active admin
- **THEN** the page shows the refusal's explanation and the person remains on the active roster
