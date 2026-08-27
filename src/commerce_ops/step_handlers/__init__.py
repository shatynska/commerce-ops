"""Every step handler this deployment answers for, grouped by discipline.

The third kind of top-level package, after the bounded contexts and
`shared`, and not a bounded context itself: it has no model, no ubiquitous
language and no invariants of its own. It is a container of adapters into
`launch`'s automation port, which is why README's rule that a second level
of nesting signals a sibling top-level module does not apply below here.

Holds handlers and nothing else. It never grows a `domain/`,
`application/` or `infrastructure/` layer of its own.
"""
