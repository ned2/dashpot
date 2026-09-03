"""Check the repository's Markdown documents for staleness signals.

Two gates run over the tracked Markdown files. The link gate resolves every
in-repo link — relative paths and heading anchors — and fails on a target that
does not exist, so a rename or a moved section cannot silently rot a pointer.
The frontmatter gate requires every document under `docs/` to declare its
`status` and `date`, and requires a `superseded` or `amended` document to name
what replaced or changed it, so a reader can tell a living document from a
finished research note without reading it.

The gate errs towards silence: code is masked before anything is read out of a
document, because a false failure on a legitimate document is worse than a
missed link. Everything it does report has been resolved against the tree.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DOCS_DIRECTORY = "docs"
ADR_DIRECTORY = "docs/adr"

# What a `status:` may say. ADRs track a decision's standing; every other
# document declares how it should be read.
ADR_STATUSES = frozenset({"proposed", "accepted", "amended", "superseded"})
DOCUMENT_STATUSES = frozenset({"living", "research", "proposal", "superseded"})

# A status that claims another document changed this one has to name it. Both
# fields hold paths relative to the naming document's own directory, the way
# its prose links are written, and every entry is resolved.
SUCCESSION_FIELDS = {"superseded": "superseded-by", "amended": "amended-by"}

FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
FRONTMATTER_FIELD_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z][\w-]*):\s*(?P<value>.*?)\s*$"
)
DATE_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")

# Inline links, and reference definitions but not footnote definitions, whose
# `[^1]: text` body is prose rather than a target.
INLINE_LINK_PATTERN = re.compile(
    r"(?<!\\)!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*<?([^()<>\s]+)>?[^()]*\)"
)
REFERENCE_DEFINITION_PATTERN = re.compile(
    r"^ {0,3}\[(?!\^)[^\]]+\]:[^\S\n]*<?(\S+)>?", re.MULTILINE
)

ATX_HEADING_PATTERN = re.compile(
    r"^ {0,3}(?P<hashes>#{1,6})[^\S\n]+(?P<text>.*?)(?:[^\S\n]+#*)?[^\S\n]*$",
    re.MULTILINE,
)
# A setext underline turns the paragraph line above it into a heading.
SETEXT_UNDERLINE_PATTERN = re.compile(r"^ {0,3}(?:=+|-+)[^\S\n]*$")
# An explicit anchor a document places by hand, on any element that carries one.
HTML_ANCHOR_PATTERN = re.compile(
    r"<[A-Za-z][^>]*?\s(?:name|id)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)

FENCE_PATTERN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
INDENTED_CODE_PATTERN = re.compile(r"^(?: {4}|\t)")
LIST_ITEM_PATTERN = re.compile(r"^ *(?:[-*+]|\d+[.)])[^\S\n]")
BLANK_PATTERN = re.compile(r"^[^\S\n]*$")
# Backtick runs delimit an inline code span; the closing run matches in length.
CODE_SPAN_PATTERN = re.compile(
    r"(?<!`)(?P<ticks>`+)(?!`).*?(?<!`)(?P=ticks)(?!`)", re.DOTALL
)

EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "ftp://", "tel:")

# GitHub's blob-view line fragment (`#L12`, `#L12-L20`) addresses a file's
# lines rather than a heading, so only its path half can be checked.
LINE_FRAGMENT_PATTERN = re.compile(r"\AL\d+(?:-L\d+)?\Z")


@dataclass(frozen=True, slots=True)
class Problem:
    """One failure a gate found, addressed to a line of a document."""

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Render the problem as one `path:line: message` line."""
        return f"{self.path}:{self.line}: {self.message}"


def tracked_markdown_files() -> list[Path]:
    """List the repository's tracked Markdown files."""
    completed = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [PROJECT_ROOT / name for name in completed.stdout.split("\0") if name]


def mask_code(text: str, *, spans: bool = True) -> str:
    """Blank every code block, and by default every code span, character for character.

    The result is the same length as the input, so an offset into it is an
    offset into the document and the reported line numbers stay true. Heading
    text keeps its spans, because a slug is built from what a span renders as.
    """
    lines = text.split("\n")
    masked: list[str] = []
    fence: str | None = None
    indented = False
    for index, line in enumerate(lines):
        blank = BLANK_PATTERN.match(line) is not None
        match = FENCE_PATTERN.match(line)
        if fence is not None:
            # Only a bare run of the same character, at least as long, closes it.
            if (
                match is not None
                and match.group("fence").startswith(fence[0])
                and len(match.group("fence")) >= len(fence)
                and not match.group("info").strip()
            ):
                fence = None
            masked.append(" " * len(line))
            continue
        if match is not None:
            fence = str(match.group("fence"))
            masked.append(" " * len(line))
            continue
        if indented and (blank or INDENTED_CODE_PATTERN.match(line)):
            masked.append(" " * len(line))
            continue
        indented = False
        # An indented block opens only after a blank line, and never where a
        # list is running: a wrapped list item is prose, and its links count.
        if INDENTED_CODE_PATTERN.match(line) and opens_indented_code(lines, index):
            indented = True
            masked.append(" " * len(line))
            continue
        if not spans:
            masked.append(line)
            continue
        masked.append(
            CODE_SPAN_PATTERN.sub(lambda span: " " * len(span.group(0)), line)
        )
    return "\n".join(masked)


def opens_indented_code(lines: Sequence[str], index: int) -> bool:
    """Report whether an indented line starts a code block rather than prose."""
    for previous in reversed(lines[:index]):
        if BLANK_PATTERN.match(previous) is not None:
            continue
        # Prose that a list introduced continues into its indented lines.
        return LIST_ITEM_PATTERN.match(
            previous
        ) is None and not INDENTED_CODE_PATTERN.match(previous)
    return False


def slugify_heading(text: str) -> str:
    """Slugify a heading the way GitHub anchors it."""
    without_links = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    without_code = without_links.replace("`", "")
    # `*` never appears inside a word; `_` does, and GitHub keeps an intraword
    # one, so only a delimiter run at a word boundary is emphasis.
    without_emphasis = re.sub(r"\*{1,3}(?=\S)(.*?)(?<=\S)\*{1,3}", r"\1", without_code)
    without_emphasis = re.sub(
        r"(?<!\w)_{1,3}(?=\S)(.*?)(?<=\S)_{1,3}(?!\w)", r"\1", without_emphasis
    )
    lowered = without_emphasis.strip().lower()
    kept = re.sub(r"[^\w\- ]", "", lowered)
    return kept.replace(" ", "-")


def iter_headings(masked: str) -> Iterable[str]:
    """Yield the text of every ATX and setext heading, in document order."""
    lines = masked.split("\n")
    for index, line in enumerate(lines):
        atx = ATX_HEADING_PATTERN.match(line)
        if atx is not None:
            yield atx.group("text")
            continue
        if index == 0 or SETEXT_UNDERLINE_PATTERN.match(line) is None:
            continue
        above = lines[index - 1]
        if (
            BLANK_PATTERN.match(above) is None
            and ATX_HEADING_PATTERN.match(above) is None
        ):
            yield above.strip()


def document_anchors(text: str) -> set[str]:
    """Collect the anchors a document's headings and explicit ids define."""
    masked = mask_code(text, spans=False)
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for heading in iter_headings(masked):
        slug = slugify_heading(heading)
        if not slug:
            continue
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    anchors.update(match.group(1) for match in HTML_ANCHOR_PATTERN.finditer(masked))
    return anchors


def line_of(text: str, offset: int) -> int:
    """Report the 1-indexed line an offset falls on."""
    return text.count("\n", 0, offset) + 1


def iter_link_targets(masked: str) -> Iterable[tuple[str, int]]:
    """Yield every link target in a document with its character offset."""
    for pattern in (INLINE_LINK_PATTERN, REFERENCE_DEFINITION_PATTERN):
        for match in pattern.finditer(masked):
            yield match.group(1), match.start(1)


def resolve_in_repository(path: Path, location: str) -> Path | None:
    """Resolve a link's path half, or report that it leaves the repository."""
    resolved = (path.parent / location).resolve()
    if resolved != PROJECT_ROOT and PROJECT_ROOT not in resolved.parents:
        return None
    return resolved


def check_links(paths: Sequence[Path]) -> list[Problem]:
    """Resolve every in-repo link and report the ones that lead nowhere."""
    anchors_by_path: dict[Path, set[str]] = {}

    def anchors_for(target: Path) -> set[str]:
        if target not in anchors_by_path:
            anchors_by_path[target] = document_anchors(
                target.read_text(encoding="utf-8")
            )
        return anchors_by_path[target]

    problems: list[Problem] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for target, offset in iter_link_targets(mask_code(text)):
            if target.startswith(EXTERNAL_SCHEMES) or target.startswith("//"):
                continue
            line = line_of(text, offset)
            location, _, raw_anchor = target.partition("#")
            anchor = unquote(raw_anchor)
            if LINE_FRAGMENT_PATTERN.match(anchor):
                anchor = ""
            if not location:
                if anchor and anchor not in anchors_for(path):
                    problems.append(
                        Problem(relative, line, f"no heading anchors #{anchor}")
                    )
                continue
            location = unquote(location.partition("?")[0])
            resolved = resolve_in_repository(path, location)
            if resolved is None:
                problems.append(
                    Problem(relative, line, f"link leaves the repository: {location}")
                )
                continue
            if not resolved.exists():
                problems.append(
                    Problem(relative, line, f"link target is missing: {location}")
                )
                continue
            if (
                anchor
                and resolved.suffix == ".md"
                and anchor not in anchors_for(resolved)
            ):
                problems.append(
                    Problem(
                        relative, line, f"{location} has no heading anchoring #{anchor}"
                    )
                )
    return problems


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Read a document's leading YAML frontmatter as flat string fields."""
    match = FRONTMATTER_PATTERN.match(text)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group("body").split("\n"):
        field = FRONTMATTER_FIELD_PATTERN.match(line)
        if field is not None:
            fields[field.group("name")] = field.group("value").strip("\"'")
    return fields


def check_succession(
    path: Path, relative: str, status: str, fields: dict[str, str]
) -> list[Problem]:
    """Require a changed document to name what changed it, and resolve each name."""
    field = SUCCESSION_FIELDS.get(status)
    if field is None:
        return []
    named = fields.get(field, "")
    if not named.strip():
        return [Problem(relative, 2, f"status {status!r} declares no {field}")]
    problems: list[Problem] = []
    for entry in (item.strip() for item in named.split(",")):
        if not entry:
            continue
        resolved = resolve_in_repository(path, entry)
        if resolved is None or not resolved.exists():
            problems.append(
                Problem(relative, 2, f"{field} names a missing document: {entry}")
            )
    return problems


def check_frontmatter(paths: Sequence[Path]) -> list[Problem]:
    """Require a declared `status` and `date` on every document under docs/."""
    problems: list[Problem] = []
    for path in paths:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if not relative.startswith(f"{DOCS_DIRECTORY}/"):
            continue
        allowed = (
            ADR_STATUSES
            if relative.startswith(f"{ADR_DIRECTORY}/")
            else DOCUMENT_STATUSES
        )
        fields = parse_frontmatter(path.read_text(encoding="utf-8"))
        if fields is None:
            problems.append(
                Problem(relative, 1, "no frontmatter; expected a status and a date")
            )
            continue
        status = fields.get("status")
        if status is None:
            problems.append(Problem(relative, 2, "frontmatter declares no status"))
        elif status not in allowed:
            expected = ", ".join(sorted(allowed))
            problems.append(
                Problem(relative, 2, f"status {status!r} is not one of: {expected}")
            )
        else:
            problems.extend(check_succession(path, relative, status, fields))
        date = fields.get("date")
        if date is None:
            problems.append(Problem(relative, 2, "frontmatter declares no date"))
        elif not DATE_PATTERN.match(date):
            problems.append(Problem(relative, 2, f"date {date!r} is not YYYY-MM-DD"))
    return problems


def select(
    tracked: Sequence[Path], names: Sequence[str]
) -> tuple[list[Path], list[str]]:
    """Narrow the tracked files to the named ones, reporting any it does not track."""
    by_resolved = {path.resolve(): path for path in tracked}
    selected: list[Path] = []
    unknown: list[str] = []
    for name in names:
        path = by_resolved.get(Path(name).resolve())
        if path is None:
            unknown.append(name)
        else:
            selected.append(path)
    return selected, unknown


def main(argv: Sequence[str] | None = None) -> int:
    """Run the documentation gates over the tracked Markdown files."""
    parser = argparse.ArgumentParser(description="Check tracked Markdown documents.")
    parser.add_argument(
        "paths", nargs="*", help="files to check; default is every tracked one"
    )
    arguments = parser.parse_args(argv)

    tracked = tracked_markdown_files()
    if arguments.paths:
        paths, unknown = select(tracked, arguments.paths)
        for name in unknown:
            print(f"{name}: not a tracked Markdown file", file=sys.stderr)
        if unknown:
            return 1
    else:
        paths = tracked

    problems = check_frontmatter(paths) + check_links(paths)
    for problem in sorted(
        problems, key=lambda item: (item.path, item.line, item.message)
    ):
        print(problem.render(), file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} documentation problem(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
