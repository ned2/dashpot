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
    write_document(
        tmp_path,
        "docs/adr/0003-later.md",
        "---\nstatus: accepted\ndate: 2026-08-28\n---\n",
    )
    amended = write_document(
        tmp_path,
        "docs/adr/0001-decide.md",
        "---\nstatus: amended\ndate: 2026-08-26\namended-by: 0003-later.md\n---\n\n# Decide\n",
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


def test_a_link_after_a_fence_reports_its_own_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Masking code keeps every offset, so a fence cannot shift a reported line."""
    document = write_document(
        tmp_path,
        "guide.md",
        "# Title\n\n```bash\nuv run dashpot work start 35 --json --timeout 10\n```\n\n"
        "See [the note](gone.md).\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:7: link target is missing: gone.md"]


def test_a_footnote_definition_is_not_a_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "guide.md", "Text[^1]\n\n[^1]: a note about stuff\n"
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_a_reference_definition_is_a_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(tmp_path, "guide.md", "Text[label]\n\n[label]: gone.md\n")

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:3: link target is missing: gone.md"]


def test_a_longer_fence_is_closed_only_by_its_own_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "guide.md", "````markdown\n```\n[x](nope.md)\n```\n````\n"
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_an_inline_code_span_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "guide.md", "Write it as `[x](nope.md)` here.\n"
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_an_indented_code_block_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(tmp_path, "guide.md", "Example:\n\n    [x](nope.md)\n")

    assert check(monkeypatch, tmp_path, document) == []


def test_an_indented_list_continuation_is_still_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A wrapped list item is prose, however deeply it is indented."""
    document = write_document(
        tmp_path, "guide.md", "- A point that runs on\n\n    and cites [x](nope.md).\n"
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:3: link target is missing: nope.md"]


def test_an_intraword_underscore_survives_the_slug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GitHub keeps `work_store` whole; only a delimiter run at a word edge is emphasis."""
    target = write_document(
        tmp_path,
        "target.md",
        "# The work_store and issue_hint fields\n\n## An _emphasised_ word\n",
    )
    document = write_document(
        tmp_path,
        "guide.md",
        "[One](target.md#the-work_store-and-issue_hint-fields) and"
        " [two](target.md#an-emphasised-word).\n",
    )

    assert check(monkeypatch, tmp_path, document, target) == []


def test_a_setext_heading_defines_an_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(tmp_path, "target.md", "Title Here\n==========\n")
    document = write_document(tmp_path, "guide.md", "[go](target.md#title-here)\n")

    assert check(monkeypatch, tmp_path, document, target) == []


def test_an_explicit_html_anchor_is_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(tmp_path, "target.md", '# Title\n\n<a name="spot"></a>\n')
    document = write_document(tmp_path, "guide.md", "[go](target.md#spot)\n")

    assert check(monkeypatch, tmp_path, document, target) == []


def test_a_bare_hash_defines_no_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(tmp_path, "guide.md", "#\n\nHello\n\n[go](#hello)\n")

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:5: no heading anchors #hello"]


def test_a_percent_encoded_link_is_decoded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(tmp_path, "café corner.md", "# Café corner\n")
    document = write_document(
        tmp_path, "guide.md", "[go](caf%C3%A9%20corner.md#caf%C3%A9-corner)\n"
    )

    assert check(monkeypatch, tmp_path, document, target) == []


def test_a_query_string_is_not_part_of_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = write_document(tmp_path, "target.md", "# Title\n")
    document = write_document(tmp_path, "guide.md", "[go](target.md?plain=1)\n")

    assert check(monkeypatch, tmp_path, document, target) == []


def test_a_link_out_of_the_repository_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repository"
    document = write_document(root, "guide.md", "[go](../outside.md)\n")
    (tmp_path / "outside.md").write_text("# Outside\n", encoding="utf-8")

    messages = check(monkeypatch, root, document)

    assert messages == ["guide.md:1: link leaves the repository: ../outside.md"]


def test_a_superseded_document_must_name_its_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = write_document(
        tmp_path, "docs/note.md", "---\nstatus: superseded\ndate: 2026-08-26\n---\n"
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["docs/note.md:2: status 'superseded' declares no superseded-by"]


def test_a_succession_field_is_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_document(
        tmp_path,
        "docs/adr/0003-real.md",
        "---\nstatus: accepted\ndate: 2026-08-26\n---\n",
    )
    document = write_document(
        tmp_path,
        "docs/adr/0001-decide.md",
        "---\nstatus: amended\ndate: 2026-08-26\namended-by: 0003-real.md, 0099-gone.md\n---\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == [
        "docs/adr/0001-decide.md:2: amended-by names a missing document: 0099-gone.md"
    ]


def test_an_untracked_path_argument_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in a path must fail rather than quietly check nothing."""
    monkeypatch.setattr(check_docs, "tracked_markdown_files", list)

    assert check_docs.main(["docs/does-not-exist.md"]) == 1


def test_the_repository_documents_pass_both_gates() -> None:
    """Guard the real tree, so a stale link or an undeclared status fails here too."""
    assert check_docs.main([]) == 0
