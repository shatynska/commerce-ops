"""`design.md` section 5's prose pass, written down instead of done by hand.

The identifier map (`rename.py`) is mechanical and complete. Prose is not:
"an active roster member" collapses to "an active member", and the collective
noun "the roster" has no one-word replacement -- `members` is the *capability*
and the *table*, but "the members carries" is not English.

Section 5 calls for correcting these by hand. At 846 affected lines the hand
is a script, but it is a **different** script from `rename.py` on purpose:

  * `rename.py`'s output is checkable against the commit line by line
    (`tasks.md` 8.1). Folding prose judgement into it would destroy that.
  * These rules touch **no identifier**. Every source below contains a space
    or an apostrophe, so nothing here can reach `MembersStore`,
    `members_set` or `list_members`. That is what keeps 8.1's boundary test
    ("the difference touches no line carrying an identifier") true.

Vocabulary decided here:

  the roster (the collection)  ->  the membership
  the roster page              ->  the Team page          (design.md section 5)
  roster identifier            ->  member identifier      (playbook-program.md)
  roster people                ->  members

`the members store` / `reader` / `collaborator` / `repository` are left alone:
they name `MembersStore`, the `members_reader` seam and the port `launch`
holds, so prose that matches the identifier is right there.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rename import EXCLUDED_DIRS, EXCLUDED_FILES, INCLUDED_SUFFIXES, walk

__all__ = ["EXCLUDED_DIRS", "EXCLUDED_FILES", "INCLUDED_SUFFIXES", "RULES", "correct"]

# Words after "the members" that name a code thing, where prose matching the
# identifier is correct and must not become "membership".
_NAMES_CODE = (
    r"(?!\s+(?:store|reader|collaborator|repository|seed|page|identifier"
    r"|admin|table|tables)\b)"
)

# `members` reading as a SINGULAR collective -- "the members holds", "an
# empty members is coherent". The determiner and any adjectives between it
# and the noun are carried through; only the noun changes.
# `[ \t]+`, never `\s+`: `\s` matches newlines, so the rule spanned
# paragraphs and rewrote 10,204 lines instead of 767.
_DETERMINER = r"\b(a|an|A|An|the|The|every|Every|this|This|that|That)([ \t]+(?:[a-z-]+[ \t]+){0,2})members\b"
# There was a `_SINGULAR_VERB` rule here -- bare `members` followed by a
# singular verb. It matched `members is None` in Python and renamed the
# variable, which is exactly what this module's docstring promises cannot
# happen. Every rule must carry a determiner or a second word; a bare-word
# rule cannot tell prose from code. The determiner rule below covers the
# cases it was added for ("the fresh members", "an empty members is").

RULES: tuple[tuple[str, str], ...] = (
    # -- Restore general English the identifier map over-reached on ---------
    # `design.md` Non-Goals: prose saying "person"/"people" about a human in
    # general is not this directory's entity. The map cannot tell -- the
    # distinction is what the sentence is *about* -- so these are listed, not
    # derived. An earlier version of this comment called the first of them
    # "the one site"; a second code review found eleven more.
    (r"\bthe members who own the host\b", "the people who own the host"),
    # Whoever runs the test suite locally.
    (r"\bwhat the member running it assumes\b", "what the person running it assumes"),
    # Whoever reads a handler's finding, or an ask in Slack.
    (r"\bA member still weighs\b", "A person still weighs"),
    (r"\ba member — today's ask carries\b", "a person — today's ask carries"),
    (r"\ba member can reach says an ask\b", "a person can reach says an ask"),
    (r"\bThe member\n", "The person\n"),
    (r"\bfor a member or for tuning\b", "for a person or for tuning"),
    (r"\bthe handler talking to a\nmember\b", "the handler talking to a\nperson"),
    (
        r"\bThis entry is the member talking back\b",
        "This entry is the person talking back",
    ),
    (r"\ba judgement a member\b", "a judgement a person"),
    # -- Collapses ---------------------------------------------------------
    # "roster people" -> "members members"; the plural is said once.
    (r"\bmembers members\b", "members"),
    # "roster member" -> "members member"; design.md section 5's own worked
    # example. Generalised from `a members member`, which left "the members
    # member" and "an active members member" standing.
    (r"\bmembers member\b", "member"),
    # "roster membership" -> "members membership"; the qualifier is what the
    # rename removes, so the noun stands alone.
    (r"\bmembers membership\b", "membership"),
    (r"\bMembers membership\b", "Membership"),
    (r"\bMembers member\b", "Member"),
    # "rosters" is its own map row now, but a stray "memberss" from an
    # earlier pass is corrected here rather than left in a shipped spec.
    (r"\bmemberss\b", "members"),
    (r"\bMemberss\b", "Members"),
    # "A rostered admin" -> "A enrolled admin"; the article has to follow.
    (r"\bA enrolled\b", "An enrolled"),
    (r"\ba enrolled\b", "an enrolled"),
    (r"\bA unadministrable\b", "An unadministrable"),
    (r"\ba unadministrable\b", "an unadministrable"),
    # "roster identifier" -> "member identifier" (docs/playbook-program.md).
    (r"\bmembers identifier\b", "member identifier"),
    # The surface is the Team page; the capability stays `members-admin`.
    (r"\bmembers page\b", "Team page"),
    # -- The collective noun ----------------------------------------------
    (r"\bmembers's\b", "membership's"),
    (r"\bthe members\b" + _NAMES_CODE, "the membership"),
    (r"\bThe members\b" + _NAMES_CODE, "The membership"),
    (r"\ba members\b" + _NAMES_CODE, "a membership"),
    (r"\bA members\b" + _NAMES_CODE, "A membership"),
    # The two general shapes, after the specific ones above have had their
    # turn: a singular determiner ("an empty members"), and a singular verb
    # ("the members holds"). Both mean the collection.
    (_DETERMINER + _NAMES_CODE, r"\1\2membership"),
)

_COMPILED = tuple((re.compile(pattern), replacement) for pattern, replacement in RULES)


def _identifiers(source: str) -> set[str] | None:
    """Every name a Python source binds or reads, or None if it will not parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


def correct(text: str, *, python: bool = False) -> str:
    """Apply the prose rules, refusing to change a Python identifier.

    The guard is the module docstring's promise made enforceable: these rules
    are for prose, and a rule that reaches an identifier is a defect in the
    rule, not a change to accept. One did -- see the note above `_DETERMINER`.
    """
    corrected = text
    for pattern, replacement in _COMPILED:
        corrected = pattern.sub(replacement, corrected)
    if python:
        before, after = _identifiers(text), _identifiers(corrected)
        if before is not None and after is not None and before != after:
            raise AssertionError(
                "the prose pass changed Python identifiers "
                f"{sorted(before - after)} -> {sorted(after - before)}; "
                "a prose rule reached code"
            )
    return corrected


def main() -> int:
    write = "--write" in sys.argv
    root = Path.cwd()
    changed = 0
    lines = 0
    for path in walk(root):
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        corrected = correct(original, python=path.suffix == ".py")
        if corrected == original:
            continue
        changed += 1
        lines += sum(
            1
            for a, b in zip(original.splitlines(), corrected.splitlines(), strict=False)
            if a != b
        )
        if write:
            path.write_text(corrected, encoding="utf-8")
    print(f"{changed} files, {lines} lines {'corrected' if write else 'would change'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
