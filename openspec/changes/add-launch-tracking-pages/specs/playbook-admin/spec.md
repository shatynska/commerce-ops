## MODIFIED Requirements

<!-- The requirement title below keeps the words "the other admin surface":
     a MODIFIED requirement must carry its requirement and scenario titles
     forward unchanged, so the title predates the third surface while its
     body does not. The same note stands above this capability's two
     headings that kept the word "live", for the same reason. -->

### Requirement: The page carries a header from which the other admin surface is reachable

Every page this capability serves — the step list, the edit surface and
the create surface — SHALL carry a header naming the admin surfaces the
session can reach, and from it **each** of those other surfaces SHALL be
reachable in one action.

The requirement was written when there were two admin surfaces and named
the roster page as the destination. There are more than two now, and the
guarantee was never about that page in particular: what it asks is that
an admin who reaches any admin surface can reach the others from it
without knowing a URL. The header SHALL name every surface the session
can reach, so that a surface added later is added to one partial rather
than left unreachable from the pages that predate it.

The header exists because the surfaces are otherwise unconnected. The
admin session lands on this page and nothing on it, or on any page
reachable from it, mentions that the other surfaces exist. An admin who
does not already know the URL cannot get there, and the roster is where
people — including the assignees this page's own form offers — are
added and deactivated.

The header SHALL identify which surface is currently being viewed, so it
reads as a position rather than as an undifferentiated set of links.
The create and edit surfaces are not themselves named in the header;
each SHALL identify the playbook surface as current, since that is the
surface an admin is within while authoring a step.

Reachability SHALL NOT depend on scripting, and SHALL NOT depend on the
step set: the header renders the same whether the set holds one step or
every one, and whatever narrowing is active. This is the guarantee the
create control already carries on this page, for the same reason — a
control that is only reachable after scrolling past 105 steps is one an
admin concludes does not exist.

Travelling to another admin surface SHALL NOT be treated as a write and
SHALL carry nothing forward: what the narrowing requirement governs is
movement between **this** capability's own views, not departure from
them, so none of this capability's narrowing state travels. Stated by
what is carried rather than by what the destination lacks — another
surface may well have narrowing of its own, and that is beside the
point.

One consequence is accepted rather than repaired, and is stated because
it is invited by this requirement's own rationale. The roster is where
assignees are added, so an admin part-way through a create who finds an
assignee missing is exactly the person the header serves — and departing
from a filled authoring surface **discards what was typed**. The
surrounding spec works hard to keep a rejected create's values,
including each named assignee, but that guarantee is about a rejection,
not about a deliberate departure. The header SHALL therefore be no
harder to leave from than any other link, and recovery is the browser's
back-navigation. A confirmation prompt was considered and refused: it
would make the common case — travelling from an untouched list — worse
in order to protect the rare one, and this capability nowhere else
guards a navigation.

#### Scenario: Departing from the create surface carries nothing forward

- **WHEN** the header's roster link is taken from the create surface
- **THEN** the roster page is served
- **AND** nothing the create surface held is persisted

#### Scenario: The roster page is reachable from the step list

- **WHEN** the step list is rendered
- **THEN** its header offers the roster page in one action
- **AND** identifies the step list as the surface currently viewed

#### Scenario: The header does not depend on how many steps are shown

- **WHEN** the step list is rendered under a narrowing that matches no
  step at all
- **THEN** the header is still rendered and still offers the roster page

#### Scenario: The authoring surfaces carry the header too

- **WHEN** the create surface and a step's edit surface are each
  rendered
- **THEN** each carries the header offering the roster page
- **AND** each identifies the playbook surface as the one currently
  viewed

#### Scenario: Every other admin surface is reachable from the step list

- **WHEN** the step list is rendered
- **THEN** its header offers each admin surface the session can reach, other than this capability's own, in one action

#### Scenario: A surface added later is named by the header

- **WHEN** an admin surface beyond the playbook and roster pages is reachable by the session
- **THEN** every page this capability serves names it in the header and offers it in one action
