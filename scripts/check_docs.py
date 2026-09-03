"""Check the repository's Markdown documents for staleness signals.

Two gates run over the tracked Markdown files. The link gate resolves every
in-repo link — relative paths and heading anchors — and fails on a target that
does not exist, so a rename or a moved section cannot silently rot a pointer.
The frontmatter gate requires every document under `docs/` to declare its
`status` and `date`, so a reader can tell a living document from a finished
research note without reading it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DOCS_DIRECTORY = "docs"
ADR_DIRECTORY = "docs/adr"

# What a `status:` may say. ADRs track a decision's standing; every other
# document declares how it should be read.
ADR_STATUSES = frozenset({"proposed", "accepted", "amended", "superseded"})
DOCUMENT_STATUSES = frozenset({"living", "research", "proposal", "superseded"})

FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
FRONTMATTER_FIELD_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z][\w-]*):\s*(?P<value>.*?)\s*$"
)
DATE_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")

# Inline links and reference definitions. Image links share the inline shape.
INLINE_LINK_PATTERN = re.compile(
    r"(?<!\\)!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*<?([^()<>\s]+)>?[^()]*\)"
)
REFERENCE_DEFINITION_PATTERN = re.compile(
    r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+)>?", re.MULTILINE
)

ATX_HEADING_PATTERN = re.compile(
    r"^(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$", re.MULTILINE
)
FENCE_PATTERN = re.compile(r"^\s{0,3}(?P<fence>```+|~~~+)")

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


def strip_code(text: str) -> str:
    """Blank out fenced code blocks, keeping every line's position intact."""
    kept: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        match = FENCE_PATTERN.match(line)
        if fence is None:
            if match is not None:
                fence = str(match.group("fence"))[:3]
                kept.append("")
                continue
            kept.append(line)
            continue
        if match is not None and match.group("fence").startswith(fence):
            fence = None
        kept.append("")
    return "\n".join(kept)


def slugify_heading(text: str) -> str:
    """Slugify a heading the way GitHub anchors it."""
    without_links = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    without_code = without_links.replace("`", "")
    without_emphasis = re.sub(
        r"[*_]{1,3}(?=\S)(.*?)(?<=\S)[*_]{1,3}", r"\1", without_code
    )
    lowered = without_emphasis.strip().lower()
    kept = re.sub(r"[^\w\- ]", "", lowered)
    return kept.replace(" ", "-")


def document_anchors(text: str) -> set[str]:
    """Collect the anchors a document's headings define."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for match in ATX_HEADING_PATTERN.finditer(strip_code(text)):
        slug = slugify_heading(match.group("text"))
        if not slug:
            continue
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def line_of(text: str, offset: int) -> int:
    """Report the 1-indexed line an offset falls on."""
    return text.count("\n", 0, offset) + 1


def iter_link_targets(text: str) -> Iterable[tuple[str, int]]:
    """Yield every link target in a document with its character offset."""
    body = strip_code(text)
    for pattern in (INLINE_LINK_PATTERN, REFERENCE_DEFINITION_PATTERN):
        for match in pattern.finditer(body):
            yield match.group(1), match.start(1)


def check_links(paths: Sequence[Path]) -> list[Problem]:
    """Resolve every in-repo link and report the ones that lead nowhere."""
    anchors_by_path: dict[Path, set[str]] = {}

    def anchors_for(path: Path) -> set[str]:
        if path not in anchors_by_path:
            anchors_by_path[path] = document_anchors(path.read_text(encoding="utf-8"))
        return anchors_by_path[path]

    problems: list[Problem] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for target, offset in iter_link_targets(text):
            if target.startswith(EXTERNAL_SCHEMES) or target.startswith("//"):
                continue
            line = line_of(text, offset)
            location, _, anchor = target.partition("#")
            if LINE_FRAGMENT_PATTERN.match(anchor):
                anchor = ""
            if not location:
                if anchor and anchor not in anchors_for(path):
                    problems.append(
                        Problem(relative, line, f"no heading anchors #{anchor}")
                    )
                continue
            resolved = (path.parent / location).resolve()
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
        date = fields.get("date")
        if date is None:
            problems.append(Problem(relative, 2, "frontmatter declares no date"))
        elif not DATE_PATTERN.match(date):
            problems.append(Problem(relative, 2, f"date {date!r} is not YYYY-MM-DD"))
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Run the documentation gates over the tracked Markdown files."""
    parser = argparse.ArgumentParser(description="Check tracked Markdown documents.")
    parser.add_argument(
        "paths", nargs="*", help="files to check; default is every tracked one"
    )
    arguments = parser.parse_args(argv)

    tracked = tracked_markdown_files()
    if arguments.paths:
        selected = {Path(name).resolve() for name in arguments.paths}
        paths = [path for path in tracked if path.resolve() in selected]
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
