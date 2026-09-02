"""The roster -> members substitution, as a script rather than 4,800 edits.

Committed with the change so the rename is *generated and diffed* rather than
hand-typed and reviewed by eye: the review question becomes "is this map
right?" (a table a person can hold) instead of "did 4,800 edits stay
faithful?" (a negative nobody can confirm). See `design.md` sections 1, 2
and 8.

Three row kinds, matched in this order at every position:

1. `PRESERVE`  -- never rewritten. Text that names the old vocabulary
   *because it is about the vocabulary*, rather than using it.
2. `OVERRIDES` -- explicit judgement rows, longest-first.
3. `STEMS`     -- the case-preserving fallback every remaining token takes.

One pass, one alternation, longest-match-first, so no output is ever fed
back through the table and a preserved token can never be a target.

    python rename.py --check    report what would change, write nothing
    python rename.py --write    apply it
    python rename.py --table    print every distinct token and its mapping
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Exclusions (design.md section 1). The input set is the whole tree minus
# these, and this list is the ONLY place the scope is decided.
# --------------------------------------------------------------------------

EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".ruff_cache",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        # The archives are history, and THIS CHANGE'S OWN DIRECTORY is under
        # here too: it is named for the old vocabulary and quotes it as the
        # evidence for renaming it (design.md section 7).
        "changes",
        # Applied revisions; their identifiers are what deployed databases
        # hold (design.md section 4).
        "versions",
    }
)

# `docs/domain-map.md` is excluded whole. `docs/deferred-work.md` records
# that this change deliberately leaves its stale `Principal` vocabulary
# alone -- and the map was editing it in seven other places, which made that
# record false. Its `access` section is also about identity in general ("May
# this person call this?" where the model is `Principal`: "identity (Slack
# user / API caller)"), and an API caller is not a directory member, so the
# substitution narrowed the meaning as well.
EXCLUDED_FILES = frozenset({"uv.lock", "domain-map.md"})

# Path prefixes excluded whole.
#
# `docs/reference/` is SOURCE MATERIAL, not vocabulary this project owns: it
# is the document the seeded step content is transcribed from, and step
# identifiers carry a provenance trace back to its row IDs. Both stems mean
# something else in it, and the map cannot tell:
#
#   "EU Responsible Person"   a legal term under GPSR -- not a directory entry
#   "line people up to buy"   customers
#   "the agent roster"        a list of AI agents
#
# Rewriting it changed seeded step *content*, which `tests/integration/
# launch/test_seeded_step_fields.py` caught by re-deriving each step's name
# from its reference row. That is a behaviour change, in the one change whose
# whole warrant is that it has none.
# `alembic/data/` is the same content one step further along: the vendored
# step set transcribed FROM `docs/reference/`, plus the two small modules
# that generate and name it. It carries **no** occurrence of `roster` at all
# -- every hit there was general English ("a member writes and a member
# reviews") or transcribed step text -- so excluding it whole loses nothing
# and stops the map editing seeded data. `test_playbook_reference_set.py`
# catches this by re-deriving the vendored set from the reference document.
EXCLUDED_PREFIXES = ("docs/reference/", "alembic/data/")

# Only text we own. A binary or a vendored asset is never rewritten.
#
# `.css` is here because `vocabulary.css` carries five prose comments naming
# the roster page; it was missed on the first pass, which is exactly the
# failure the whole-tree input set exists to prevent and the reason the
# completeness gate greps rather than trusting this list.
#
# `.js` is deliberately absent: the only JavaScript in the tree is the
# vendored `htmx.min.js`, which we do not own and must never rewrite.
INCLUDED_SUFFIXES = frozenset(
    {
        ".py",
        ".md",
        ".html",
        ".css",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".txt",
        ".sql",
    }
)

# --------------------------------------------------------------------------
# 1. PRESERVE (design.md section 2)
#
# Three of these are DERIVED by the rule "a token naming something inside an
# exclusion, that also occurs outside the exclusions" -- evaluated in two
# columns, because a preserve row does two jobs at different moments:
#
#   map protection      needed where the token occurs outside the exclusions
#                       WHEN THE MAP RUNS
#   check-2 permission  needed where it occurs outside them IN THE COMMITTED
#                       TREE
#
# `rename-the-roster-to-members` takes no protection row -- at map time it
# exists only inside its own excluded directory -- but earns permission,
# because tasks 7.5 and 7.6 write it into two docs. It is listed here anyway
# so that one table answers both questions.
#
# `a3d7e9f2c481_add_roster_tables` takes NEITHER column and is deliberately
# absent: it occurs only under `alembic/versions/**`, so the exclusion
# already protects it, and a permission row would fail the completeness
# gate's symmetric half on a correct tree.
# --------------------------------------------------------------------------

# Preserve rows that apply ONLY inside one file.
#
# The quotations below are quotations *in `docs/playbook-program.md`*. Two of
# them are also live text elsewhere -- "An active roster member resolves to
# the unrestricted scope" is a real requirement heading in
# `openspec/specs/access-scope/spec.md`, which is exactly what this change
# must rename. A global preserve row protects the quotation and freezes the
# requirement, and the completeness gate then reports the requirement as a
# missed rename. Scope decides which is which.
SCOPED_PRESERVE: dict[str, tuple[str, ...]] = {
    "AGENTS.md": (
        # The ONE stem inside `AGENTS.md`'s tool-managed block (lines 1-180,
        # between the `ai-toolkit:development-workflow` markers). Two reasons
        # to leave it: the block is regenerated by `sync generated
        # development-workflow block`, so an edit here is reverted without
        # anyone noticing it was ever made; and the sentence is about the
        # next human to read the repository, not a directory member.
        "it is what the next person, or",
    ),
    "docs/playbook-program.md": (
        # Quotes the PRE-rename specs; it is the evidence for the rename, so
        # rewriting it makes the argument circular.
        "An active roster member resolves to the unrestricted scope",
        # The third of the three neighbouring quotations. Carries `person`
        # rather than `roster`, and would otherwise be rewritten into
        # something the quoted spec never said.
        "membership says what a person may see",
    ),
}

# Any path INTO the change directories, preserved whole -- the change name
# AND everything after it.
#
# Two failures this fixes, both found only by running the map:
#
#   * A bare prefix (`openspec/changes/move-principals-to-roster/`) protects
#     the name and leaves the TAIL to be rewritten, so five test modules
#     citing `.../specs/roster/spec.md` came out pointing at
#     `.../specs/members/spec.md`, which does not exist. The word is gone, so
#     the completeness gate PASSES while test-to-spec traceability breaks.
#   * `vocabulary.css` and six test modules cite
#     `pick-steps-and-people-by-checkbox`, a second archived change nobody
#     had enumerated.
PRESERVE_PATTERNS: tuple[str, ...] = (r"openspec/changes/[A-Za-z0-9._/-]+",)


def _change_names() -> tuple[str, ...]:
    """Every change directory's name, archived ones with the date stripped.

    DERIVED, not enumerated -- `design.md` section 2's rule, implemented
    rather than transcribed. Transcribing it is what missed
    `pick-steps-and-people-by-checkbox`: an enumeration is only as good as
    whoever wrote it, and this one was written twice and short twice.
    """
    root = Path(__file__).resolve().parents[3]
    changes = root / "openspec" / "changes"
    names: set[str] = set()
    for entry in changes.iterdir() if changes.is_dir() else ():
        if not entry.is_dir():
            continue
        if entry.name == "archive":
            for archived in entry.iterdir():
                if archived.is_dir():
                    # Strip the `YYYY-MM-DD-` the archive prefixes with.
                    names.add(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", archived.name))
        else:
            names.add(entry.name)
    # Only the ones the map would otherwise touch need a row; the rest would
    # produce a permission hit the completeness gate then has to explain.
    return tuple(
        sorted(
            (n for n in names if re.search(r"roster|person|people", n)),
            key=len,
            reverse=True,
        )
    )


PRESERVE: tuple[str, ...] = (
    # Derived from disk by `_change_names()`: `move-principals-to-roster`,
    # `pick-steps-and-people-by-checkbox`, and this change's own name.
    *_change_names(),
    # Enumerated residue: prose quoting a prior state, which no rule derives.
    # Global because this sentence exists nowhere else; the two quotations
    # beside it in the same paragraph are file-scoped above, because their
    # text IS live elsewhere.
    #
    # Becomes "is `members`, not `members`" -- an argument that destroys
    # itself.
    "The people directory is `members`, not `roster`",
)

# --------------------------------------------------------------------------
# 2. OVERRIDES -- the rows that carry judgement rather than mechanism.
# Applied longest-first, so `roster_people` is consumed before `roster`.
# --------------------------------------------------------------------------

OVERRIDES: dict[str, str] = {
    # -- The admin surface renames to `team`, not to `members` -------------
    # `roster -> members` cannot produce any of this. The header row is
    # matched WHOLE so its key, path and label move together and cannot
    # half-apply -- which is also what keeps the bare label `Users` out of
    # the map (it occurs seven times, only two of them this edit; the two
    # display strings in the template are hand-edited under design.md
    # section 5).
    '("roster", "/admin/roster", "Users")': '("team", "/admin/team", "Team")',
    # The OTHER half of the header key, in a different file: the page tells
    # the partial which surface is current. The whole-tuple row above cannot
    # reach it, and without this row the key becomes `"members"` while the
    # tuple says `"team"` -- so the equality never holds, the page renders
    # its own entry as a link instead of the current surface, and two tests
    # fail. Exactly the half-apply the tuple row exists to prevent, one file
    # further out.
    '{% with current = "roster" %}': '{% with current = "team" %}',
    "/admin/roster": "/admin/team",
    "roster.html": "team.html",
    # -- Tables and the constraint ----------------------------------------
    # The table names the collection, not "rows of members".
    # Plural. Without this row `roster` fires and yields "memberss", which
    # reached a normative SHALL in a shipped spec.
    "rosters": "members",
    "Rosters": "Members",
    "ROSTERS": "MEMBERS",
    "roster_people": "members",
    "roster_set": "members_set",
    "ck_roster_set_singleton": "ck_members_set_singleton",
    # -- The ORM row ------------------------------------------------------
    # NOT `Member`: the ORM row and the domain value are different things in
    # different layers, and the existing name already distinguishes them by
    # prefix. Collapsing them would make models.py's import shadow the
    # domain entity.
    "RosterPerson": "MemberRow",
    "RosterSet": "MembersSet",
    # -- Module paths (the files themselves are moved by `git mv`) --------
    "access/application/roster.py": "access/application/members.py",
    "access/domain/principals.py": "access/domain/members.py",
    "access.application.roster": "access.application.members",
    "access.domain.principals": "access.domain.members",
    "roster_repository": "members_repository",
    "roster_admin": "members_admin",
    # -- Test constants: SINGULAR, since each names one person's identifier
    "ALICE_ROSTER_ID": "ALICE_MEMBER_ID",
    "BOHDAN_ROSTER_ID": "BOHDAN_MEMBER_ID",
    "CHLOE_ROSTER_ID": "CHLOE_MEMBER_ID",
    "CONFIRMER_ROSTER_ID": "CONFIRMER_MEMBER_ID",
    "STRANGER_ROSTER_ID": "STRANGER_MEMBER_ID",
    "ROSTER_ADMIN_IDENTITY": "MEMBER_ADMIN_IDENTITY",
    "ROSTERED_ADMIN_IDENTITY": "ENROLLED_ADMIN_IDENTITY",
    "ROSTER_ADMIN_NAME": "MEMBER_ADMIN_NAME",
    "_roster_person_id": "_member_id",
    "roster_identifier": "member_identifier",
    "a-roster-identifier": "a-member-identifier",
    "roster-identifier": "member-identifier",
    # -- Prose-shaped test names ------------------------------------------
    # `NOT_ON_THE_ROSTER -> NOT_ON_THE_MEMBERS` is not English.
    "NOBODY_ON_THE_ROSTER": "NOBODY_IS_A_MEMBER",
    "_NOT_ON_THE_ROSTER": "_NOT_A_MEMBER",
    "NOT_ON_THE_ROSTER": "NOT_A_MEMBER",
    "an-actor-not-on-the-roster": "an-actor-who-is-not-a-member",
    "-never-on-any-roster": "-never-a-member-anywhere",
    "_BLAMES_ROSTER_MEMBERSHIP": "_BLAMES_MEMBERSHIP",
    "rostered": "enrolled",
    "unrostered": "unenrolled",
    # -- `people` where it is this concept's plural ------------------------
    "list_people": "list_members",
    "_roster_people": "_members",
    "read_people": "read_members",
}

# --------------------------------------------------------------------------
# 3. STEMS -- the case-preserving fallback. Every remaining token takes one.
# --------------------------------------------------------------------------

STEMS: dict[str, str] = {
    "roster": "members",
    "person": "member",
    "people": "members",
    "persons": "members",
}


def _case_variants(source: str, target: str) -> dict[str, str]:
    """lower, Title and UPPER forms of one stem row."""
    return {
        source.lower(): target.lower(),
        source.capitalize(): target.capitalize(),
        source.upper(): target.upper(),
    }


# A lowercase stem must not match INSIDE a word: `impersonates` contains
# `person` and became `immemberates`. Guarded by requiring no lowercase
# letter on either side. Title-case (`FakePerson`) and UPPER (`ALICE_ROSTER`)
# are left unguarded, because CamelCase and SCREAMING_CASE are exactly where
# a stem legitimately abuts a letter.
_SUBWORD_BEFORE = r"(?<![a-z])"
_SUBWORD_AFTER = r"(?![a-z])"


def build_table(
    relative_path: str = "",
) -> tuple[re.Pattern[str], dict[str, str], frozenset[str]]:
    """One alternation over every row, longest-first.

    Longest-first is what makes the table safe: `roster_people` is consumed
    before `roster` ever sees it, and a `preserve` string is matched before
    any substitution can reach inside it.
    """
    mapping: dict[str, str] = {}
    scoped = SCOPED_PRESERVE.get(relative_path, ())
    preserved = frozenset(PRESERVE) | frozenset(scoped)

    for token in (*PRESERVE, *scoped):
        mapping[token] = token
    for source, target in OVERRIDES.items():
        mapping.setdefault(source, target)
    for source, target in STEMS.items():
        for variant, replacement in _case_variants(source, target).items():
            mapping.setdefault(variant, replacement)

    # A multi-word `preserve` row must survive being WRAPPED. The quotations
    # in `docs/playbook-program.md` sit inside a paragraph, so "An active
    # roster member resolves..." is stored as "An active\nroster member
    # resolves..." and a literal match finds nothing -- the row silently does
    # not fire, the quotation is rewritten, and the completeness gate passes
    # because the word is gone. Every run of spaces in a preserve row is
    # therefore matched as arbitrary whitespace.
    def as_pattern(token: str) -> str:
        escaped = re.escape(token)
        if token in preserved and " " in token:
            return escaped.replace("\\ ", r"\s+")
        if token.islower() and token.isalpha():
            return _SUBWORD_BEFORE + escaped + _SUBWORD_AFTER
        return escaped

    ordered = sorted(mapping, key=len, reverse=True)
    alternation = "|".join((*PRESERVE_PATTERNS, *(as_pattern(x) for x in ordered)))
    return re.compile(alternation), mapping, preserved


def assert_deterministic() -> None:
    """Every position has exactly one parse (`tasks.md` 1.6).

    NOT injectivity. The map is deliberately non-injective -- `roster`,
    `roster_people`, `people` and `persons` all target `members`, because a
    roster, a set of people and a set of persons *are* all members now.
    Injectivity mattered only to the abandoned reverse-substitution proof;
    the forward generate-and-diff check needs an unambiguous parse, which
    longest-match-first in a single pass gives by construction.

    What is worth checking is that the construction actually holds: that
    where one row's source contains another's, the longer wins, and that
    applying the table twice changes nothing the second time.
    """
    pattern, mapping, preserved = build_table()

    sources = sorted(mapping, key=len, reverse=True)

    # Ask the COMPILED PATTERN which alternative wins, not the list it was
    # built from. An earlier version of this check compared positions in
    # `sources` -- which is already sorted longest-first, and only ever
    # compared a token against ones later in that list, so the assertion was
    # true by construction and could never fire. The property `tasks.md` 1.6
    # calls machine-checked was therefore unchecked.
    for index, longer in enumerate(sources):
        for shorter in sources[index + 1 :]:
            if shorter not in longer:
                continue
            matched = pattern.match(longer)
            won = matched.group(0) if matched is not None else None
            assert won == longer, (
                f"{shorter!r} is matched inside {longer!r} "
                f"(the pattern yields {won!r}): "
                f"the alternation does not prefer the longer row"
            )

    # A preserved string must survive its own table.
    for token in preserved:
        once = pattern.sub(lambda m: _resolve(m, mapping), token)
        assert once == token, f"preserve row {token!r} was rewritten to {once!r}"

    # Idempotence: the second pass is a no-op, so no output is ever re-fed.
    probe = " ".join(sources)
    once = pattern.sub(lambda m: _resolve(m, mapping), probe)
    twice = pattern.sub(lambda m: _resolve(m, mapping), once)
    assert once == twice, "the table is not idempotent; output re-enters it"


def _resolve(match: re.Match[str], mapping: dict[str, str]) -> str:
    """The replacement for one match.

    A wrapped `preserve` row matches text that is not a key -- "An active\\n
    roster member..." rather than "An active roster member..." -- so an
    unknown match can only be such a row, and the answer is to leave it
    exactly as it was found, newline included.
    """
    found = match.group(0)
    return mapping.get(found, found)


def substitute(text: str, relative_path: str = "") -> str:
    pattern, mapping, _ = build_table(relative_path)
    return pattern.sub(lambda match: _resolve(match, mapping), text)


def in_scope(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if relative.as_posix().startswith(EXCLUDED_PREFIXES):
        return False
    if path.name in EXCLUDED_FILES:
        return False
    return path.suffix in INCLUDED_SUFFIXES


def walk(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and in_scope(p, root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    parser.add_argument("--write", action="store_true", help="apply the substitution")
    parser.add_argument("--table", action="store_true", help="print the token mapping")
    parser.add_argument("--root", default=".", help="tree root (default: cwd)")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    # Runs on every invocation, not as a separate step: a table that is not
    # deterministic must never reach a file.
    assert_deterministic()

    if args.table:
        pattern, mapping, preserved = build_table()
        found: dict[str, int] = {}
        for path in walk(root):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for match in pattern.finditer(text):
                found[match.group(0)] = found.get(match.group(0), 0) + 1
        for token in sorted(found, key=lambda t: (-found[t], t)):
            kind = "PRESERVE" if token in preserved else "->"
            target = "" if token in preserved else mapping[token]
            print(f"{found[token]:>5}  {token!r:<48} {kind} {target!r}")
        return 0

    changed: list[tuple[Path, int]] = []
    for path in walk(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rewritten = substitute(text, str(path.relative_to(root)))
        if rewritten == text:
            continue
        hits = sum(
            1
            for a, b in zip(text.splitlines(), rewritten.splitlines(), strict=False)
            if a != b
        )
        changed.append((path, hits))
        if args.write:
            path.write_text(rewritten, encoding="utf-8")

    verb = "rewrote" if args.write else "would rewrite"
    for path, hits in changed:
        print(f"{hits:>5} lines  {verb}  {path.relative_to(root)}")
    print(f"\n{len(changed)} files, {sum(h for _, h in changed)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
