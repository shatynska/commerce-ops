"""A small HTML tree, and the queries the admin-surface tests ask of it.

Every rendered-page test in this suite parses HTML and asserts on the result,
and each one used to carry its own copy of this parser -- 37 files, ~150 lines
apiece. The parser is deliberately forgiving in the same way `html.parser` is:
an unclosed tag is closed by whatever end tag eventually matches an open
ancestor, which is what a browser does and what these tests have always relied
on.

**Not every file that had one gets this one.** Three data models exist in the
suite, and only the one below is shared:

    STANDARD  Node(tag, attrs, parent, children)  +  Text(text)     25 files
    ORDERED   Node(..., order, children)          +  Text(text)      8 files
    ORDINAL   Node(tag, attrs, parent, children)  +  Text(ordinal, text)
                                                                     4 files

The last two track document order, which the queries here do not model. Their
files keep their own parser: replacing it would change what those tests can
ask, and a migration that changes an assertion is not a migration.

Names are public here and aliased at the call site, because a module-private
name imported across modules is a contradiction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final

#: Tags that never take an end tag, so the parser must not push them.
VOID_TAGS: Final = (
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
)

#: The htmx verbs an element may carry to declare a request.
HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")

#: Class names this project's templates use to hide an element.
HIDDEN_CLASSES: Final = (
    "hidden",
    "is-hidden",
    "d-none",
    "sr-only",
    "visually-hidden",
)


@dataclass
class Text:
    """A run of text, whitespace already flattened."""

    text: str


@dataclass
class Node:
    """One element, its attributes, its parent and its children."""

    tag: str
    attrs: dict[str, str]
    parent: Node | None
    children: list[Node | Text] = field(default_factory=list)


def flat(text: str) -> str:
    """Text with every run of whitespace collapsed to one space."""
    return " ".join(text.split())


class TreeParser(HTMLParser):
    """A forgiving tree builder.

    An unclosed tag is closed by whatever end tag eventually matches an open
    ancestor -- `handle_endtag` searches the stack rather than assuming the top
    of it, so malformed markup yields a tree instead of an exception.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {}, None)
        self._stack: list[Node] = [self.root]

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(
            Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1])
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].children.append(Text(flat(data)))


def tree(html: str) -> Node:
    """The document `html` parses to."""
    parser = TreeParser()
    parser.feed(html)
    return parser.root


def elements(node: Node) -> Iterator[Node]:
    """Every element beneath `node`, depth first."""
    for child in node.children:
        if isinstance(child, Node):
            yield child
            yield from elements(child)


def texts(node: Node) -> list[str]:
    """Each run of text beneath `node`, in order, unaltered."""
    found: list[str] = []
    for child in node.children:
        if isinstance(child, Text):
            found.append(child.text)
        else:
            found.extend(texts(child))
    return found


def all_text(node: Node) -> str:
    """Everything beneath `node` as one lowercased string."""
    found: list[str] = []
    for child in node.children:
        if isinstance(child, Text):
            found.append(child.text)
        else:
            found.append(all_text(child))
    return " ".join(part for part in found if part).lower()


def attribute_text(node: Node) -> str:
    """The attribute values a reader could see, lowercased."""
    parts = [
        value
        for element in (node, *elements(node))
        for key, value in element.attrs.items()
        if key in ("class", "title", "aria-label", "id") or key.startswith("data-")
    ]
    return " ".join(parts).lower()


def classes(node: Node) -> set[str]:
    """The element's class names."""
    return set(node.attrs.get("class", "").split())


def carries(node: Node, marker: str) -> bool:
    """Whether the element carries `marker` as a class."""
    return marker in classes(node)


def element_hidden(node: Node) -> bool:
    """Whether this element alone is hidden, ignoring its ancestors."""
    attrs = node.attrs
    if "hidden" in attrs and attrs["hidden"].lower() != "false":
        return True
    if attrs.get("aria-hidden", "").lower() == "true":
        return True
    style = attrs.get("style", "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return any(
        name in HIDDEN_CLASSES for name in attrs.get("class", "").lower().split()
    )


def element_disabled(node: Node) -> bool:
    """Whether this element alone is disabled."""
    return (
        "disabled" in node.attrs
        or node.attrs.get("aria-disabled", "").lower() == "true"
    )


def inherited(node: Node, predicate: Callable[[Node], bool]) -> bool:
    """Whether `predicate` holds for the node or any ancestor below `#document`."""
    walker: Node | None = node
    while walker is not None and walker.tag != "#document":
        if predicate(walker):
            return True
        walker = walker.parent
    return False


def ancestors(node: Node) -> Iterator[Node]:
    """Each ancestor below `#document`, nearest first."""
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def nearest(node: Node, tag: str) -> Node | None:
    """The closest ancestor with `tag`, if any."""
    return next((a for a in ancestors(node) if a.tag == tag), None)


def size(node: Node) -> int:
    """The element and everything beneath it, counted."""
    return 1 + sum(1 for _ in elements(node))
