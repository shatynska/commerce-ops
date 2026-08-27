## ADDED Requirements

### Requirement: Registering a handler does not load what the handler needs to run

Registering a step handler SHALL make its name resolvable and SHALL NOT, by itself, load or construct the resources the handler uses when it runs — a language model client, a graph, an HTTP session, or anything else it reaches for only while resolving a step. Those SHALL be obtained when the handler is invoked, and MAY be retained between invocations.

This is a **deployment** property, not a matter of taste. Every process that consults the registry must register every handler in order to consult it at all, so each such process pays every handler's registration cost — including processes that never invoke one, such as the process that makes the startup handler report. A registration that loads a model client makes the cost of reading a name proportional to the weight of the work behind it, multiplied by the number of handlers the deployment answers for.

Where obtaining a resource is deferred, the deferral SHALL NOT change what the handler produces: a handler resolving a step SHALL behave as it would have with the resource obtained at registration.

#### Scenario: Registering a handler loads no model client

- **WHEN** a step handler's module is loaded such that its name becomes resolvable in the registry
- **THEN** its name resolves, and the process holds no resource the handler uses to resolve a step

#### Scenario: A handler still resolves a step

- **WHEN** a registered handler whose resources are obtained on invocation is run over a step, against a model that answers as the deterministic agent-graph tests specify
- **THEN** it produces the outcome and the result text those tests specify, unchanged by when its resources were obtained

#### Scenario: A process that never invokes a handler still pays only for the registration

- **WHEN** a process registers every handler this deployment answers for in order to read the registry, and invokes none of them
- **THEN** it loads no handler's working resources
