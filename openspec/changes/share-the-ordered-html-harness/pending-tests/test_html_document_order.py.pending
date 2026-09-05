"""`document_order`'s contract, stated directly.

`share-the-ordered-html-harness` replaces a stored `order` field on eight local
parsers with one derived query, and the equivalence between the two was proved
by execution -- 11 files, 138 parses, 19,056 nodes, zero order mismatches. That
proof establishes the function's *answer* over the trees the tier happens to
parse. What it cannot establish is the function's *method*, and that is what
this file pins:

* **The target is located by identity, never by `==`** (`design.md` constraint
  2). `Node` is a `@dataclass` with value equality, and two sibling `<td>` with
  the same tag, attributes and text compare equal -- their shared `parent`
  object short-circuits the tuple comparison rather than recursing. An
  implementation reaching for `list.index`, `in`, or any `==` scan answers the
  *first* equal node, which is a plausible integer and a silent wrong answer.
  Every mismatch it would produce is invisible to the migration's own proof,
  because the tier's `.order` reads compare two integers and never inspect how
  either was found.
* **The document root answers `0` and the first element `1`**
  (`design.md` Decision 1), which is the numbering the eight local parsers
  produce (`test_launch_detail_breadcrumb.py:466-472`). The five migrating read
  sites compare two answers with `<` or sort by one, so an implementation
  numbering from `0` at the first element would leave all five green while
  moving what "document order" means.
* **A text run takes no position.** `_open` increments once per *element*;
  `handle_data` appends a `Text` and increments nothing. A walk counting text
  runs answers plausibly and disagrees with every `.order` this change replaces.
* **A detached node answers `0` and its child answers `1`** -- the wording
  `design.md` Decision 1 pins so the rule cannot be read as "a detached subtree
  answers 0 throughout".

One finding recorded here rather than asserted, because it is a property of
`Node` and not of `document_order`: two structurally similar elements under
*different* parents cannot be compared with `==` at all -- `Node.__eq__`
recurses through `parent` and `children` and raises `RecursionError`. So an
`==`-based implementation is not merely wrong on equal siblings; on an ordinary
table page it crashes. The tests below therefore never compare two nodes from
different parents by value.

This is the shared harness's own behaviour, so it lives under
`tests/unit/support/` -- the deliberate exception to the tier layout, per
`AGENTS.md`.
"""

from __future__ import annotations

from dataclasses import fields

from tests.support.html import Node, document_order, elements, tree

#: One ordinary admin-shaped page. Its pre-order element sequence is
#: html, head, title, body, nav, a, a, main, h1, table, tr, td, td, br, img,
#: span, p -- 17 elements, numbered 1..17, with the document root at 0.
#: Confirmed against `tests.support.html.tree` rather than read off the source.
PAGE = """
<html>
  <head><title>Launches</title></head>
  <body>
    <nav class="crumbs"><a href="/">Home</a><a href="/launches">Launches</a></nav>
    <main>
      <h1 class="title">Launches</h1>
      <table>
        <tr><td>same</td><td>same</td></tr>
      </table>
      <br>
      <img src="/logo.png"/>
      <span/>
      <p>after</p>
    </main>
  </body>
</html>
"""

#: Two rows holding one equal cell each. The cells are *not* siblings, so they
#: must never be compared with `==` (see the module docstring).
ROWS = "<table><tr><td>same</td></tr><tr><td>same</td></tr></table>"

#: A text run and an element under one parent: `<b>` is the second element,
#: not the third, because `alpha` takes no position.
RUN = "<p>alpha<b>beta</b></p>"


def _named(root: Node, tag: str) -> list[Node]:
    """Every element with `tag` beneath `root`, in document order."""
    return [node for node in elements(root) if node.tag == tag]


def _first(root: Node, tag: str) -> Node:
    """The first element with `tag` beneath `root`."""
    return _named(root, tag)[0]


def test_the_document_root_answers_zero() -> None:
    assert document_order(tree(PAGE)) == 0


def test_the_first_element_answers_one() -> None:
    assert document_order(_first(tree(PAGE), "html")) == 1


def test_siblings_ascend_in_document_order() -> None:
    root = tree(PAGE)
    first, second = _named(root, "a")

    assert document_order(first) < document_order(second)


def test_a_descendant_answers_after_its_ancestor() -> None:
    root = tree(PAGE)
    table = _first(root, "table")
    cell = _named(root, "td")[0]

    assert document_order(table) < document_order(cell)


def test_two_equal_siblings_answer_distinct_positions() -> None:
    """The `==`-vs-`is` trap, and the only failure a plausible integer hides.

    The two cells are equal and are not the same object; an implementation
    locating either of them by `==` answers 12 for both.
    """
    root = tree(PAGE)
    left, right = _named(root, "td")
    assert left == right
    assert left is not right

    assert document_order(left) == 12
    assert document_order(right) == 13


def test_an_equal_cell_in_an_earlier_row_does_not_claim_the_answer() -> None:
    """The same trap where the equal node is not a sibling.

    Derived (see the manifest): `tasks.md` 3.2 names the sibling case. This
    variant is the shape an `index()`-style implementation meets on a real
    table -- and, per the module docstring, the two cells here cannot be
    compared with `==` at all, so the test does not.
    """
    root = tree(ROWS)
    first, second = _named(root, "td")

    assert document_order(first) == 3
    assert document_order(second) == 5


def test_a_void_element_takes_a_position() -> None:
    """`<br>` is opened and never pushed; it still occupies one index."""
    root = tree(PAGE)
    void = _first(root, "br")

    assert document_order(void) == 14
    assert document_order(_first(root, "img")) == document_order(void) + 1


def test_a_self_closing_element_takes_a_position() -> None:
    """`<span/>` arrives through `handle_startendtag` and takes one index."""
    root = tree(PAGE)
    closed = _first(root, "span")

    assert document_order(closed) == 16
    assert document_order(_first(root, "p")) == document_order(closed) + 1


def test_a_text_run_takes_no_position() -> None:
    root = tree(RUN)

    assert document_order(_first(root, "p")) == 1
    assert document_order(_first(root, "b")) == 2


def test_every_element_answers_its_index_in_the_shared_pre_order_walk() -> None:
    """Agreement with `elements()`, which is what Decision 1 derives from."""
    root = tree(PAGE)
    walk = list(elements(root))
    assert len(walk) == 17

    assert [document_order(node) for node in walk] == list(range(1, 18))


def test_the_answer_is_counted_from_the_document_root() -> None:
    """The walk climbs `parent`; it does not start at the node it was given."""
    root = tree(PAGE)
    main = _first(root, "main")
    heading = _first(root, "h1")
    assert next(iter(elements(main))) is heading

    assert document_order(heading) == 9


def test_a_detached_node_answers_zero() -> None:
    """A node whose `parent` chain reaches no `#document` is its own root."""
    detached = Node("div", {}, None)

    assert document_order(detached) == 0


def test_a_detached_nodes_child_answers_one() -> None:
    """So the rule is not "a detached subtree answers 0 throughout"."""
    detached = Node("div", {}, None)
    child = Node("span", {}, detached)
    detached.children.append(child)

    assert document_order(child) == 1


def test_the_node_type_gains_no_order_field() -> None:
    """`design.md` constraint 1: nothing is added to `Node`.

    Twenty files already import it and rely on its `__eq__` and `__repr__`, so
    an implementation that stores the index rather than deriving it is a
    breaking change wearing a passing suite. This assertion holds today and its
    job is to keep holding.
    """
    assert tuple(field.name for field in fields(Node)) == (
        "tag",
        "attrs",
        "parent",
        "children",
    )
