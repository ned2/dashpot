from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The maintenance script is intentionally not part of the installed package.
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import check_docs  # ruff: ignore[module-import-not-at-top-of-file]

sys.path.pop(0)


def write_document(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def check(monkeypatch: pytest.MonkeyPatch, root: Path, *paths: Path) -> list[str]:
    """Run both gates against a disposable tree and return their messages."""
    monkeypatch.setattr(check_docs, "PROJECT_ROOT", root)
    problems = check_docs.check_frontmatter(paths) + check_docs.check_links(paths)
    return [problem.render() for problem in problems]


def test_a_link_to_a_missing_file_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(tmp_path, "guide.md", "See [the note](docs/gone.md).\n")

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:1: link target is missing: docs/gone.md"]


def test_a_link_to_a_missing_anchor_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(tmp_path, "target.md", "# Real heading\n")
    document = write_document(tmp_path, "guide.md", "See [it](target.md#imagined).\n")

    messages = check(monkeypatch, tmp_path, document, target)

    assert messages == ["guide.md:1: target.md has no heading anchoring #imagined"]


def test_a_link_to_a_present_anchor_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(
        tmp_path, "target.md", "# Observe `Branches` without fetching\n\n## Usage\n"
    )
    document = write_document(
        tmp_path,
        "guide.md",
        "[One](target.md#observe-branches-without-fetching) and [two](target.md#usage).\n",
    )

    assert check(monkeypatch, tmp_path, document, target) == []


def test_a_same_document_anchor_is_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "guide.md", "Jump to [keys](#keys) and [gone](#gone).\n\n## Keys\n"
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:1: no heading anchors #gone"]


def test_repeated_headings_take_numbered_anchors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path,
        "guide.md",
        "[First](#consequences) and [second](#consequences-1).\n\n"
        "## Consequences\n\n## Consequences\n",
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_links_inside_fenced_code_are_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "guide.md", "```markdown\n[example](docs/never-existed.md)\n```\n"
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_a_line_fragment_checks_only_its_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(tmp_path, "target.md", "# Heading\n")
    document = write_document(tmp_path, "guide.md", "See [lines](target.md#L4-L9).\n")

    assert check(monkeypatch, tmp_path, document, target) == []


def test_an_external_link_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "guide.md", "See [upstream](https://example.invalid/nowhere#top).\n"
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_a_document_without_frontmatter_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(tmp_path, "docs/note.md", "# Note\n")

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["docs/note.md:1: no frontmatter; expected a status and a date"]


def test_a_document_outside_docs_needs_no_frontmatter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(tmp_path, "README.md", "# Dashpot\n")

    assert check(monkeypatch, tmp_path, document) == []


def test_an_unknown_status_and_a_malformed_date_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "docs/note.md", "---\nstatus: draft\ndate: August\n---\n\n# Note\n"
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == [
        "docs/note.md:2: status 'draft' is not one of: living, proposal, research, superseded",
        "docs/note.md:2: date 'August' is not YYYY-MM-DD",
    ]


def test_an_adr_takes_the_decision_statuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    amended = write_document(
        tmp_path,
        "docs/adr/0001-decide.md",
        "---\nstatus: amended\ndate: 2026-08-26\namended-by: 0003\n---\n\n# Decide\n",
    )
    research = write_document(
        tmp_path,
        "docs/adr/0002-decide.md",
        "---\nstatus: research\ndate: 2026-08-26\n---\n",
    )

    messages = check(monkeypatch, tmp_path, amended, research)

    assert messages == [
        "docs/adr/0002-decide.md:2: "
        "status 'research' is not one of: accepted, amended, proposed, superseded"
    ]


def test_the_repository_documents_pass_both_gates() -> None:
    """Guard the real tree, so a stale link or an undeclared status fails here too."""
    assert check_docs.main([]) == 0
