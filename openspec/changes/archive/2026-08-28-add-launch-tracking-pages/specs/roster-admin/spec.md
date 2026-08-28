## MODIFIED Requirements

<!-- The requirement title below keeps the words "the other admin surface",
     and the first scenario title keeps "The playbook page": a MODIFIED
     requirement must carry its requirement and scenario titles forward
     unchanged, so both predate the third surface while their bodies do
     not. `playbook-admin` already carries this note over two headings
     that kept the word "live", for the same reason. -->

### Requirement: The page carries a header from which the other admin surface is reachable

The roster page SHALL carry the same header every other admin surface
carries, naming the admin surfaces the session can reach, and from it
each of those other surfaces SHALL be reachable in one action. The header
SHALL identify the roster as the surface currently being viewed.

The requirement was written when there were two admin surfaces and named
the playbook page as "the other" one. There are more than two now, and
the guarantee was never about that page in particular: what it asks is
that an admin who reaches any admin surface can reach the others from it
without knowing a URL. The header SHALL name every surface the session
can reach, so that a surface added later is added to one partial rather
than left unreachable from the pages that predate it.

Today the page carries no link of any kind. An admin who reaches it —
which itself requires knowing the URL, since nothing links here — cannot
get back to the other surfaces without typing another one. Both
directions are the same gap and are closed together.

Reachability SHALL NOT depend on scripting.

#### Scenario: The playbook page is reachable from the roster

- **WHEN** the roster page is rendered
- **THEN** its header offers the playbook page in one action
- **AND** identifies the roster as the surface currently viewed

#### Scenario: Every other admin surface is reachable from the roster

- **WHEN** the roster page is rendered
- **THEN** its header offers each admin surface the session can reach, other than the roster itself, in one action

#### Scenario: The header is rendered on a roster holding nobody

- **WHEN** the roster page is rendered holding no people at all
- **THEN** the header is still rendered and still offers the other admin
  surfaces

#### Scenario: A surface added later is named by the header

- **WHEN** an admin surface beyond the playbook and roster pages is reachable by the session
- **THEN** the roster page's header names it and offers it in one action
