## ADDED Requirements

### Requirement: The webhook subscription is registered as an idempotent, non-blocking deploy step

The system SHALL provide a step that ensures a ClickUp webhook subscription exists for this deployment's completion endpoint, run after database migrations and before the HTTP server begins serving, as a step of its own rather than as part of the serving process's own startup — the same positioning `roster`'s admin-seeding step takes, and for the analogous reason: the step's one piece of work is a call to an external system (ClickUp), and an external call that can fail or hang must not gate the first request the server would otherwise serve.

Before creating anything, the step SHALL check whether a subscription already targets both this deployment's endpoint and the configured launch folder, and SHALL NOT create a second one where it finds such a match — an idempotent check-then-create, not an unconditional create run on every deploy. Matching on the endpoint alone would not do: a subscription found only because it shares the endpoint could belong to a since-changed folder configuration, and treating it as sufficient would silently leave the *current* folder unregistered. A created or matched subscription SHALL be scoped to the configured launch folder and to task status change events, not to the whole ClickUp workspace, since nothing outside that folder is ever mapped to a launch — which the endpoint-and-folder match keeps true of a matched subscription as well as a created one.

Where the configured launch folder has changed since a subscription was last registered, the check finds no match against the new folder and the step creates a fresh one scoped to it, exactly as it would with no prior subscription at all. The old subscription is not deleted — it is simply no longer this deployment's concern, having become, from the moment the folder configuration changed, a subscription for a folder nothing here maps to any more.

Where the configured credentials resolve to no ClickUp workspace or to more than one, the step SHALL take no action beyond logging the ambiguity — it SHALL NOT guess which workspace to register against. Where this deployment's own public endpoint is not configured, the step SHALL likewise take no action beyond logging the gap, rather than registering a subscription pointed at an unreachable or malformed address.

Unlike `roster`'s admin-seeding step, a failure here — an unresolvable workspace, an unreachable endpoint, a failed ClickUp API call, or any other fault — SHALL be logged as a warning naming the reason and SHALL NOT fail the step, block the deployment, or prevent the server from serving. The two steps share a shape and differ in this one respect deliberately: an unadministrable roster breaks a feature the moment the release starts serving, while completion delivery already has a fallback this capability provides independently of the webhook — the reconciliation pass — so a registration failure degrades to that fallback rather than to a broken deployment.

Each time the step creates a subscription — whether none existed before, or one that existed has since been removed from ClickUp by any means — ClickUp generates that subscription's signing secret itself and returns it in the creation response; the system never supplies its own. The step SHALL log that secret at warning level, naming explicitly that the deployment's configured signing secret must be set or updated to match it before any delivery will verify, and that a subscription recreated without that update leaves every delivery silently rejected by signature verification — indistinguishable, from ClickUp's side, from a healthy subscription.

#### Scenario: A first registration creates a subscription and surfaces its secret

- **WHEN** the step runs and no subscription targets this deployment's endpoint
- **THEN** a subscription is created, scoped to the configured launch folder and to task status change events
- **AND** the secret ClickUp returns for it is logged at warning level, naming that the deployment's signing secret must be set to match

#### Scenario: An existing matching subscription is not recreated

- **WHEN** the step runs and a subscription already targets both this deployment's endpoint and the configured launch folder
- **THEN** no new subscription is created

#### Scenario: A recreated subscription surfaces its secret exactly as a first registration does

- **WHEN** the step runs, no subscription currently targets both this deployment's endpoint and the configured launch folder, and one matching both previously did before being removed
- **THEN** a subscription is created and its ClickUp-generated secret is logged at warning level, exactly as on a first registration — the step does not distinguish the two, since it has no record of a subscription ever having existed before

#### Scenario: A changed launch folder gets its own fresh subscription

- **WHEN** the step runs, the configured launch folder differs from the one a prior subscription was scoped to, and that prior subscription still exists in ClickUp
- **THEN** a new subscription is created scoped to the currently configured folder, and its secret is logged exactly as on a first registration
- **AND** the prior subscription is left as it is — the step neither deletes it nor treats it as satisfying the check

#### Scenario: An ambiguous workspace takes no action

- **WHEN** the step runs and the configured credentials resolve to no ClickUp workspace or to more than one
- **THEN** no subscription is created or checked for
- **AND** the ambiguity is logged

#### Scenario: A missing public endpoint takes no action

- **WHEN** the step runs and this deployment's own public endpoint is not configured
- **THEN** no subscription is created
- **AND** the gap is logged

#### Scenario: A registration failure does not block the deployment

- **WHEN** the step runs and the call to ClickUp fails for any reason
- **THEN** the failure is logged as a warning naming the reason
- **AND** the deployment proceeds and the server begins serving, exactly as if the step had succeeded

#### Scenario: Starting the server performs no registration

- **WHEN** the serving process starts
- **THEN** it performs no webhook registration of its own, leaving that entirely to the step that already ran before it
