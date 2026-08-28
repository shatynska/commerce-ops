## ADDED Requirements

### Requirement: The dossier offers the way back to the product index

The dossier SHALL carry a breadcrumb trail naming the product index as a
link and the product itself as the current, un-linked, segment — the
current segment rendered as the page's own title, so the page carries no
separate title beside it. Following the index link SHALL reach the index
in one action, without scripting, as the index renders with no narrowing
active.

The dossier carries no way back today: it identifies no admin surface as
current in the shared header (it is a page about one product and has no
address the header could name), and nothing else on the page offers the
index. An admin who opens a dossier and wants the index back has had no
way to get there except the browser's own back button.

#### Scenario: The index is reachable from a product's dossier

- **WHEN** a product's dossier is rendered
- **THEN** its breadcrumb trail offers the product index in one action, without scripting
- **AND** the trail's last segment names the product and is not a link
