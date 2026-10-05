from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The maintenance script is intentionally not part of the installed package.
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import maintain_docs  # ruff: ignore[module-import-not-at-top-of-file]

sys.path.pop(0)


def write_document(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def check(monkeypatch: pytest.MonkeyPatch, root: Path, *paths: Path) -> list[str]:
    """Run the frontmatter and link gates against a disposable tree.

    The numbering gate reads the whole set rather than a selection, so it has
    a helper of its own.
    """
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", root)
    problems = maintain_docs.check_frontmatter(paths) + maintain_docs.check_links(paths)
    return [problem.render() for problem in problems]


def check_numbers(
    monkeypatch: pytest.MonkeyPatch, root: Path, *paths: Path
) -> list[str]:
    """Run the ADR numbering gate against a disposable tree."""
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", root)
    return [problem.render() for problem in maintain_docs.check_adr_numbers(paths)]


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


def test_a_line_fragment_within_the_file_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_document(tmp_path, "src/module.py", "a = 1\nb = 2\nc = 3\n")
    document = write_document(
        tmp_path,
        "guide.md",
        "See [one](src/module.py#L3) and [all](src/module.py#L1-L3).\n",
    )

    assert check(monkeypatch, tmp_path, document) == []


def test_a_line_fragment_beyond_the_file_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A moved or shortened file must not keep a link to lines it no longer has."""
    write_document(tmp_path, "src/module.py", "a = 1\nb = 2\nc = 3\n")
    document = write_document(
        tmp_path,
        "guide.md",
        "See [past](src/module.py#L4) and [over](src/module.py#L2-L9).\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == [
        "guide.md:1: src/module.py #L4 is beyond its 3 lines",
        "guide.md:1: src/module.py #L2-L9 is beyond its 3 lines",
    ]


def test_an_inverted_or_zero_line_fragment_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_document(tmp_path, "src/module.py", "a = 1\nb = 2\nc = 3\n")
    document = write_document(
        tmp_path,
        "guide.md",
        "See [zero](src/module.py#L0) and [back](src/module.py#L3-L2).\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == [
        "guide.md:1: src/module.py #L0 is not a line range",
        "guide.md:1: src/module.py #L3-L2 is not a line range",
    ]


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


def test_a_link_in_an_html_comment_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A commented-out link renders as nothing, so it cannot fail the gate."""
    document = write_document(
        tmp_path,
        "guide.md",
        "<!-- [old](gone.md) -->\n"
        "Before <!-- a comment that\nwraps [x](gone.md) --> after [y](missing.md).\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:3: link target is missing: missing.md"]


def test_a_comment_in_a_paragraph_ends_at_a_blank_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A marker inside a paragraph cannot hide the paragraphs after it."""
    document = write_document(
        tmp_path,
        "guide.md",
        "A stray <!-- marker\n\n[x](gone.md)\n\nUse --> arrows.\n"
        "<!--\n\n[y](hidden.md)\n\n-->\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:3: link target is missing: gone.md"]


def test_a_comment_marker_in_a_code_span_opens_no_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A span that opens first wins, so the link after it is still read."""
    document = write_document(
        tmp_path, "guide.md", "Write `<!--` to open one; see [x](gone.md) -->.\n"
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:1: link target is missing: gone.md"]


def test_an_unclosed_comment_marker_hides_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only a closed comment renders as nothing; a stray marker is text."""
    document = write_document(
        tmp_path, "guide.md", "A stray <!-- before [x](gone.md).\n"
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["guide.md:1: link target is missing: gone.md"]


def test_a_heading_in_an_html_comment_defines_no_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Neither a commented-out heading nor a commented-out anchor renders."""
    target = write_document(
        tmp_path,
        "target.md",
        '<!--\n## Draft\n\n<a name="spot"></a>\n-->\n## Kept `<!--` marker\n',
    )
    document = write_document(
        tmp_path,
        "guide.md",
        "[a](target.md#draft) [b](target.md#spot) [c](target.md#kept----marker)\n",
    )

    messages = check(monkeypatch, tmp_path, document, target)

    assert messages == [
        "guide.md:1: target.md has no heading anchoring #draft",
        "guide.md:1: target.md has no heading anchoring #spot",
    ]


def test_a_broken_link_in_a_docstring_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A module links its ADR relative to itself, so moving it must not rot the link."""
    write_document(tmp_path, "docs/adr/0001-decide.md", "# Decide\n")
    module = write_document(
        tmp_path,
        "src/pkg/module.py",
        '"""Do the thing.\n\n'
        "As [ADR 0001](../../docs/adr/0001-decide.md#decide) and\n"
        '[ADR 0002](../../docs/adr/0002-gone.md) decide.\n"""\n\n\n'
        "def act() -> None:\n"
        '    """Act ([ADR 0001](../docs/adr/0001-decide.md))."""\n',
    )

    messages = check(monkeypatch, tmp_path, module)

    assert messages == [
        "src/pkg/module.py:4: link target is missing: ../../docs/adr/0002-gone.md",
        "src/pkg/module.py:9: link target is missing: ../docs/adr/0001-decide.md",
    ]


def test_a_broken_link_in_a_python_comment_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = write_document(
        tmp_path,
        "scripts/tool.py",
        "VALUE = 1  # As [the note](gone.md) says.\n"
        "# A [wrapped\n# link](also-gone.md#L3).\n"
        "NAME: str\n"
        '"""An attribute docstring, citing [it](missing.md)."""\n',
    )

    messages = check(monkeypatch, tmp_path, module)

    assert messages == [
        "scripts/tool.py:1: link target is missing: gone.md",
        "scripts/tool.py:3: link target is missing: also-gone.md",
        "scripts/tool.py:5: link target is missing: missing.md",
    ]


def test_link_syntax_in_python_code_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only docstrings and comments are prose; a subscript call or a string is code."""
    module = write_document(
        tmp_path,
        "src/pkg/module.py",
        '"""Render links, as `[x](gone.md)` shows."""\n\n'
        "handlers = {}\n"
        'handlers["key"](1)\n'
        'label = "[x](gone.md)"\n'
        'message = f"[{label}](also-gone.md)"\n'
        '"[x](" "gone.md)" if label else ""\n'
        '"[x](" "gone.md)"\n'
        "print(\n"
        '    "[x](gone.md)"\n'
        ")\n",
    )

    assert check(monkeypatch, tmp_path, module) == []


def test_a_same_file_anchor_in_python_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Python has no headings, so a comment line is not mistaken for one."""
    module = write_document(
        tmp_path, "src/module.py", "# Usage\n# See [usage](#usage) and [it](#gone).\n"
    )

    assert check(monkeypatch, tmp_path, module) == []


def test_python_that_cannot_be_tokenized_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A file the gate cannot read is reported rather than passed unread."""
    module = write_document(tmp_path, "src/module.py", 'TEXT = """never closed\n')

    messages = check(monkeypatch, tmp_path, module)

    assert len(messages) == 1
    assert messages[0].startswith(
        "src/module.py:1: cannot read its docstrings and comments: "
    )


def test_a_tracked_python_path_argument_is_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Python file is selected by path as a document is, and its links checked."""
    module = write_document(tmp_path, "src/module.py", "# See [it](gone.md).\n")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(maintain_docs, "tracked_markdown_files", list)
    monkeypatch.setattr(maintain_docs, "tracked_python_files", lambda: [module])
    monkeypatch.setattr(maintain_docs, "check_adr_index", lambda paths: [])
    monkeypatch.setattr(maintain_docs, "check_code_map", lambda shipped: [])
    monkeypatch.setattr(maintain_docs, "tracked_package_files", list)

    assert maintain_docs.main([str(module)]) == 1
    assert "src/module.py:1: link target is missing: gone.md" in capsys.readouterr().err


def test_the_link_gate_reads_the_tracked_python_of_the_package_and_scripts() -> None:
    """Git's `*` crosses directories, so a nested module is read; tests are not."""
    read = {
        path.relative_to(maintain_docs.PROJECT_ROOT).as_posix()
        for path in maintain_docs.tracked_python_files()
    }

    assert any(name.count("/") > 2 for name in read if name.startswith("src/"))
    assert "scripts/maintain_docs.py" in read
    assert all(name.startswith(("src/", "scripts/")) for name in read)


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


def test_frontmatter_defines_no_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The `---` closing frontmatter is not a setext underline of its last field."""
    target = write_document(
        tmp_path, "target.md", "---\nstatus: living\ndate: 2026-09-12\n---\n\n# Title\n"
    )
    document = write_document(tmp_path, "guide.md", "[go](target.md#date-2026-09-12)\n")

    messages = check(monkeypatch, tmp_path, document, target)

    assert messages == [
        "guide.md:1: target.md has no heading anchoring #date-2026-09-12"
    ]


def test_an_html_anchor_in_frontmatter_defines_no_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GitHub renders frontmatter as a table, so an id written there anchors nothing."""
    target = write_document(
        tmp_path, "target.md", '---\nnote: <a id="spot"></a>\n---\n\n# Title\n'
    )
    document = write_document(tmp_path, "guide.md", "[go](target.md#spot)\n")

    messages = check(monkeypatch, tmp_path, document, target)

    assert messages == ["guide.md:1: target.md has no heading anchoring #spot"]


def test_a_link_after_frontmatter_reports_its_own_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A link past the frontmatter is still reported on the line it is written on."""
    document = write_document(
        tmp_path,
        "docs/guide.md",
        "---\nstatus: living\ndate: 2026-09-12\n---\n\n# Title\n\n"
        "See [it](#date-2026-09-12) and [title](#title).\n",
    )

    messages = check(monkeypatch, tmp_path, document)

    assert messages == ["docs/guide.md:8: no heading anchors #date-2026-09-12"]


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
    monkeypatch.setattr(maintain_docs, "tracked_markdown_files", list)
    monkeypatch.setattr(maintain_docs, "tracked_python_files", list)

    assert maintain_docs.main(["docs/does-not-exist.md"]) == 1


def test_two_adrs_sharing_a_number_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A bare "ADR NNNN" has to identify one ADR, so the gate rejects a collision."""
    alpha = write_document(tmp_path, "docs/adr/0034-publish-an-alpha.md", "")
    toml = write_document(tmp_path, "docs/adr/0034-read-settings-as-toml.md", "")
    lone = write_document(tmp_path, "docs/adr/0035-open-worktrees.md", "")

    messages = check_numbers(monkeypatch, tmp_path, alpha, toml, lone)

    assert messages == [
        "docs/adr/0034-publish-an-alpha.md:1: ADR number 0034 is also taken by "
        "docs/adr/0034-read-settings-as-toml.md",
        "docs/adr/0034-read-settings-as-toml.md:1: ADR number 0034 is also taken by "
        "docs/adr/0034-publish-an-alpha.md",
    ]


def test_distinct_adr_numbers_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = write_document(tmp_path, "docs/adr/0034-publish-an-alpha.md", "")
    second = write_document(tmp_path, "docs/adr/0052-read-settings-as-toml.md", "")

    assert check_numbers(monkeypatch, tmp_path, first, second) == []


def test_an_adr_filename_without_a_number_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An ADR the gate cannot number is one it cannot check for a collision."""
    unnumbered = write_document(tmp_path, "docs/adr/read-settings-as-toml.md", "")
    short = write_document(tmp_path, "docs/adr/034-publish-an-alpha.md", "")

    messages = check_numbers(monkeypatch, tmp_path, unnumbered, short)

    assert messages == [
        "docs/adr/034-publish-an-alpha.md:1: filename declares no four-digit ADR number",
        "docs/adr/read-settings-as-toml.md:1: "
        "filename declares no four-digit ADR number",
    ]


def test_the_adr_index_needs_no_number(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The index records no decision, so it claims no number."""
    index = write_document(tmp_path, "docs/adr/README.md", "")
    adr = write_document(tmp_path, "docs/adr/0034-publish-an-alpha.md", "")

    assert check_numbers(monkeypatch, tmp_path, index, adr) == []


def test_a_numbered_document_outside_the_adr_directory_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Numbering identifies decisions; it says nothing about other documents."""
    first = write_document(tmp_path, "docs/0034-a-note.md", "")
    second = write_document(tmp_path, "docs/0034-another-note.md", "")

    assert check_numbers(monkeypatch, tmp_path, first, second) == []


def write_adr(root: Path, name: str, title: str, **fields: str) -> Path:
    """Write an ADR with the frontmatter the index reads."""
    declared = {"status": "accepted", "date": "2026-08-26"} | {
        key.replace("_", "-"): value for key, value in fields.items()
    }
    frontmatter = "".join(f"{key}: {value}\n" for key, value in declared.items())
    heading = f"# {title}\n" if title else ""
    return write_document(root, name, f"---\n{frontmatter}---\n\n{heading}")


def index_of(monkeypatch: pytest.MonkeyPatch, root: Path, *paths: Path) -> str:
    """Render the ADR index for a disposable tree."""
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", root)
    return maintain_docs.render_adr_index(paths)


def test_the_index_lists_every_adr_by_number(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The index is the one place every decision is reachable from."""
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Do the second thing")
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")

    rendered = index_of(monkeypatch, tmp_path, second, first)

    assert rendered.endswith(
        "| ADR | Decision | Status | Resolved by |\n"
        "| --- | --- | --- | --- |\n"
        "| 0001 | [Do the first thing](0001-first.md) | accepted | — |\n"
        "| 0002 | [Do the second thing](0002-second.md) | accepted | — |\n"
    )


def test_the_index_names_what_resolved_an_adr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An amended or superseded ADR is listed with the ADRs that changed it."""
    amended = write_adr(
        tmp_path,
        "docs/adr/0001-first.md",
        "Do the first thing",
        status="amended",
        amended_by="0002-second.md, 0003-third.md",
    )
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Do the second thing")
    third = write_adr(tmp_path, "docs/adr/0003-third.md", "Do the third thing")

    rendered = index_of(monkeypatch, tmp_path, amended, second, third)

    assert (
        "| 0001 | [Do the first thing](0001-first.md) | amended "
        "| [0002](0002-second.md), [0003](0003-third.md) |\n"
    ) in rendered


def test_the_index_dates_itself_by_its_newest_adr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A date taken from the ADRs is a function of them, so the gate can compare whole files."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "First", date="2026-08-26")
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Second", date="2026-09-12")

    rendered = index_of(monkeypatch, tmp_path, first, second)

    assert rendered.startswith("---\nstatus: living\ndate: 2026-09-12\n---\n")


def test_a_frontmatter_field_is_not_mistaken_for_the_title(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Frontmatter closes with the `---` that also underlines a setext heading."""
    adr = write_adr(
        tmp_path,
        "docs/adr/0001-first.md",
        "Do the first thing",
        status="amended",
        amended_by="0002-second.md",
    )
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Do the second thing")

    assert "[Do the first thing](0001-first.md)" in index_of(
        monkeypatch, tmp_path, adr, second
    )


def test_a_setext_heading_titles_an_adr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An ADR may underline its title as well as hash it."""
    adr = write_document(
        tmp_path,
        "docs/adr/0001-first.md",
        "---\nstatus: accepted\ndate: 2026-08-26\n---\n\n"
        "Do the first thing\n==================\n",
    )

    assert "[Do the first thing](0001-first.md)" in index_of(monkeypatch, tmp_path, adr)


def test_a_setext_level_two_heading_does_not_title_an_adr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dash underline makes a level-two heading, which the title skips."""
    adr = write_document(
        tmp_path,
        "docs/adr/0001-first.md",
        "---\nstatus: accepted\ndate: 2026-08-26\n---\n\n"
        "Context first\n-------------\n\n# Do the first thing\n",
    )

    assert "[Do the first thing](0001-first.md)" in index_of(monkeypatch, tmp_path, adr)


def test_an_out_of_date_index_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A generated index only stays fresh if something notices it was not regenerated."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Do the second thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    write_document(
        tmp_path, "docs/adr/README.md", maintain_docs.render_adr_index([first])
    )

    problems = maintain_docs.check_adr_index([first, second])

    assert [problem.render() for problem in problems] == [
        "docs/adr/README.md:1: the ADR index is out of date; "
        "regenerate it with --write-indexes"
    ]


def test_a_missing_index_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A repository with ADRs and no index is as out of date as a stale one."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)

    problems = maintain_docs.check_adr_index([first])

    assert [problem.render() for problem in problems] == [
        "docs/adr/README.md:1: the ADR index is missing; "
        "regenerate it with --write-indexes"
    ]


def test_a_current_index_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate reports nothing when the committed index is the generated one."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    write_document(
        tmp_path, "docs/adr/README.md", maintain_docs.render_adr_index([first])
    )

    assert maintain_docs.check_adr_index([first]) == []


def test_the_index_declares_a_document_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The index records no decision, so a decision status would be meaningless."""
    index = write_document(
        tmp_path, "docs/adr/README.md", "---\nstatus: living\ndate: 2026-09-23\n---\n"
    )

    assert check(monkeypatch, tmp_path, index) == []


def test_a_pipe_in_a_title_does_not_break_the_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unescaped pipe would split the row into five cells and kill the link."""
    adr = write_adr(tmp_path, "docs/adr/0001-first.md", "Prefer TOML | JSON")

    rendered = index_of(monkeypatch, tmp_path, adr)

    assert "| 0001 | [Prefer TOML \\| JSON](0001-first.md) | accepted | — |" in rendered


def test_an_adr_without_a_heading_is_reported_not_rendered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty link would satisfy the comparison while telling a reader nothing."""
    adr = write_adr(tmp_path, "docs/adr/0001-first.md", "")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)

    problems = maintain_docs.check_adr_index([adr])

    assert [problem.render() for problem in problems] == [
        "docs/adr/0001-first.md:1: declares no level-one heading, "
        "so the ADR index cannot title it"
    ]


@pytest.mark.parametrize("flag", ["--write-indexes", "--write-adr-index"])
def test_writing_the_index_satisfies_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flag: str
) -> None:
    """The write path is the remedy both failures name, so it has to produce a pass.

    The older flag is kept for the instructions that still name it.
    """
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Do the second thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        maintain_docs, "tracked_markdown_files", lambda: [first, second]
    )
    monkeypatch.setattr(maintain_docs, "tracked_python_files", list)

    assert maintain_docs.main([flag]) == 0
    assert maintain_docs.check_adr_index([first, second]) == []


def test_writing_the_index_still_rejects_an_untracked_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A typo must not be swallowed by the flag that ignores the selection."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(maintain_docs, "tracked_markdown_files", lambda: [first])
    monkeypatch.setattr(maintain_docs, "tracked_python_files", list)

    assert maintain_docs.main(["--write-indexes", "docs/does-not-exist.md"]) == 1
    assert not (tmp_path / maintain_docs.ADR_INDEX_PATH).exists()


KIND = "docs/research"


def write_kind_document(root: Path, name: str, title: str, **fields: str) -> Path:
    """Write a document of the research kind with the frontmatter its index reads."""
    declared = {"status": "research", "date": "2026-08-26"} | fields
    frontmatter = "".join(f"{key}: {value}\n" for key, value in declared.items())
    heading = f"# {title}\n" if title else ""
    return write_document(root, f"{KIND}/{name}", f"---\n{frontmatter}---\n\n{heading}")


def write_kind_index(
    root: Path, introduction: str = "# Research\n\nNotes.\n\n", after: str = "\n"
) -> Path:
    """Write a research index whose generated parts are still empty."""
    return write_document(
        root,
        f"{KIND}/README.md",
        "---\nstatus: living\ndate: 2026-01-01\n---\n\n"
        + introduction
        + f"{maintain_docs.KIND_TABLE_START}\n\n{maintain_docs.KIND_TABLE_END}"
        + after,
    )


def kind_index_after_writing(
    monkeypatch: pytest.MonkeyPatch, root: Path, *paths: Path
) -> str:
    """Rewrite the indexes of a disposable tree and read back the research index."""
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", root)
    # Every index is rewritten, the ADR index among them.
    (root / maintain_docs.ADR_DIRECTORY).mkdir(parents=True, exist_ok=True)
    assert maintain_docs.write_indexes(paths) == []
    return (root / KIND / "README.md").read_text(encoding="utf-8")


def check_kinds(monkeypatch: pytest.MonkeyPatch, root: Path, *paths: Path) -> list[str]:
    """Run the kind index gate against a disposable tree."""
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", root)
    return [problem.render() for problem in maintain_docs.check_kind_indexes(paths)]


def test_a_kind_index_lists_its_documents_newest_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One date is listed by filename, so the order is a function of the documents."""
    older = write_kind_document(
        tmp_path, "older.md", "An older note", date="2026-08-01"
    )
    later = write_kind_document(tmp_path, "b-later.md", "Later, B", date="2026-09-01")
    same_day = write_kind_document(
        tmp_path, "a-later.md", "Later, A", date="2026-09-01"
    )
    index = write_kind_index(tmp_path)

    rendered = kind_index_after_writing(
        monkeypatch, tmp_path, older, later, same_day, index
    )

    assert rendered.endswith(
        f"{maintain_docs.KIND_TABLE_START}\n\n"
        "| Document | Status | Date |\n"
        "| --- | --- | --- |\n"
        "| [Later, A](a-later.md) | research | 2026-09-01 |\n"
        "| [Later, B](b-later.md) | research | 2026-09-01 |\n"
        "| [An older note](older.md) | research | 2026-08-01 |\n"
        f"\n{maintain_docs.KIND_TABLE_END}\n"
    )


def test_a_kind_index_lists_only_the_documents_beside_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A subdirectory's documents, such as the spikes' traces, keep their own index."""
    note = write_kind_document(tmp_path, "note.md", "A note")
    nested = write_kind_document(tmp_path, "traces/README.md", "Traces")
    elsewhere = write_document(
        tmp_path,
        "docs/elsewhere.md",
        "---\nstatus: living\ndate: 2026-08-26\n---\n\n# Elsewhere\n",
    )
    index = write_kind_index(tmp_path)

    rendered = kind_index_after_writing(
        monkeypatch, tmp_path, note, nested, elsewhere, index
    )

    assert "| [A note](note.md) |" in rendered
    assert "Traces" not in rendered
    assert "Elsewhere" not in rendered
    assert "](README.md)" not in rendered


def test_a_kind_index_keeps_its_introduction_and_dates_itself_by_its_newest_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only the frontmatter and the table are generated; the prose around them is kept."""
    first = write_kind_document(tmp_path, "first.md", "First", date="2026-08-26")
    second = write_kind_document(tmp_path, "second.md", "Second", date="2026-09-12")
    write_kind_index(
        tmp_path,
        introduction="# Research\n\nA hand-written introduction.\n\n",
        after="\n\nA closing remark.\n",
    )

    rendered = kind_index_after_writing(monkeypatch, tmp_path, first, second)

    assert rendered.startswith(
        "---\nstatus: living\ndate: 2026-09-12\n---\n\n"
        "# Research\n\nA hand-written introduction.\n\n"
        f"{maintain_docs.KIND_TABLE_START}\n"
    )
    assert rendered.endswith(f"{maintain_docs.KIND_TABLE_END}\n\nA closing remark.\n")


def test_a_pipe_in_a_document_title_does_not_break_the_kind_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unescaped pipe would split the row and kill the link."""
    note = write_kind_document(tmp_path, "note.md", "TOML | JSON")
    write_kind_index(tmp_path)

    rendered = kind_index_after_writing(monkeypatch, tmp_path, note)

    assert "| [TOML \\| JSON](note.md) | research | 2026-08-26 |" in rendered


def test_a_current_kind_index_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate reports nothing once the generated parts are what the script writes."""
    note = write_kind_document(tmp_path, "note.md", "A note")
    write_kind_index(tmp_path)
    kind_index_after_writing(monkeypatch, tmp_path, note)

    assert check_kinds(monkeypatch, tmp_path, note) == []


@pytest.mark.parametrize(
    ("name", "title", "fields", "row"),
    [
        pytest.param(
            "added.md",
            "Added",
            {},
            "| [Added](added.md) | research | 2026-08-26 |",
            id="a document missing from the table",
        ),
        pytest.param(
            "note.md",
            "A retitled note",
            {},
            "| [A retitled note](note.md) | research | 2026-08-26 |",
            id="a changed title",
        ),
        pytest.param(
            "note.md",
            "A note",
            {"status": "superseded"},
            "| [A note](note.md) | superseded | 2026-08-26 |",
            id="a changed status",
        ),
        pytest.param(
            "note.md",
            "A note",
            {"date": "2026-09-30"},
            "| [A note](note.md) | research | 2026-09-30 |",
            id="a changed date",
        ),
    ],
)
def test_a_kind_index_that_disagrees_with_its_documents_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    title: str,
    fields: dict[str, str],
    row: str,
) -> None:
    """A new document, or a document whose row has changed, leaves the table stale."""
    note = write_kind_document(tmp_path, "note.md", "A note")
    write_kind_index(tmp_path)
    kind_index_after_writing(monkeypatch, tmp_path, note)
    changed = write_kind_document(tmp_path, name, title, **fields)
    # A rewritten document is still one document, listed once.
    documents = list(dict.fromkeys([note, changed]))

    assert check_kinds(monkeypatch, tmp_path, *documents) == [
        "docs/research/README.md:1: the kind index is out of date; "
        "regenerate it with --write-indexes"
    ]
    assert row in kind_index_after_writing(monkeypatch, tmp_path, *documents)
    assert check_kinds(monkeypatch, tmp_path, *documents) == []


def test_a_kind_index_that_lists_a_removed_document_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A row for a document that no longer exists is as stale as a missing one."""
    kept = write_kind_document(tmp_path, "kept.md", "Kept")
    removed = write_kind_document(tmp_path, "removed.md", "Removed")
    write_kind_index(tmp_path)
    kind_index_after_writing(monkeypatch, tmp_path, kept, removed)
    removed.unlink()

    assert check_kinds(monkeypatch, tmp_path, kept) == [
        "docs/research/README.md:1: the kind index is out of date; "
        "regenerate it with --write-indexes"
    ]


def test_a_missing_kind_index_fails_only_where_there_is_something_to_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The introduction is hand-written, so the gate cannot write a missing index."""
    assert check_kinds(monkeypatch, tmp_path) == []

    note = write_kind_document(tmp_path, "note.md", "A note")

    assert check_kinds(monkeypatch, tmp_path, note) == [
        "docs/research/README.md:1: the kind index is missing; write its "
        "introduction above the generated table's marker comments, then "
        "regenerate it with --write-indexes"
    ]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("# Research\n\n| Document | Status | Date |\n", id="no markers"),
        pytest.param(
            f"{maintain_docs.KIND_TABLE_END}\n{maintain_docs.KIND_TABLE_START}\n",
            id="markers reversed",
        ),
        pytest.param(
            f"{maintain_docs.KIND_TABLE_START}\n{maintain_docs.KIND_TABLE_END}\n"
            f"{maintain_docs.KIND_TABLE_START}\n{maintain_docs.KIND_TABLE_END}\n",
            id="two tables",
        ),
        pytest.param(
            f"Prose {maintain_docs.KIND_TABLE_START}\n{maintain_docs.KIND_TABLE_END}\n",
            id="a marker inside a line",
        ),
    ],
)
def test_a_kind_index_without_one_marked_table_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str
) -> None:
    """Without one bounded table there is no telling which text is generated."""
    note = write_kind_document(tmp_path, "note.md", "A note")
    write_document(
        tmp_path,
        f"{KIND}/README.md",
        f"---\nstatus: living\ndate: 2026-08-26\n---\n{body}",
    )

    assert check_kinds(monkeypatch, tmp_path, note) == [
        "docs/research/README.md:1: marks no generated table; put the opening "
        "and closing marker comments every kind index carries on lines of their "
        "own below the introduction, then regenerate it with --write-indexes"
    ]


def test_a_kind_document_without_a_heading_is_reported_not_rendered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty link would satisfy the comparison while telling a reader nothing."""
    note = write_kind_document(tmp_path, "note.md", "")
    write_kind_index(tmp_path)

    assert check_kinds(monkeypatch, tmp_path, note) == [
        "docs/research/note.md:1: declares no level-one heading, "
        "so its kind index cannot title it"
    ]


def test_a_rebase_conflict_in_the_generated_parts_is_resolved_by_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two branches that each add a document conflict in the table and the date.

    Rewriting the generated parts resolves both, which is what lets such a
    rebase stay content-preserving.
    """
    ours = write_kind_document(tmp_path, "ours.md", "Ours", date="2026-09-01")
    theirs = write_kind_document(tmp_path, "theirs.md", "Theirs", date="2026-09-02")
    write_document(
        tmp_path,
        f"{KIND}/README.md",
        "---\nstatus: living\n<<<<<<< HEAD\ndate: 2026-09-01\n=======\n"
        "date: 2026-09-02\n>>>>>>> theirs\n---\n\n# Research\n\nNotes.\n\n"
        f"{maintain_docs.KIND_TABLE_START}\n\n"
        "| Document | Status | Date |\n| --- | --- | --- |\n"
        "<<<<<<< HEAD\n| [Ours](ours.md) | research | 2026-09-01 |\n=======\n"
        "| [Theirs](theirs.md) | research | 2026-09-02 |\n>>>>>>> theirs\n"
        f"\n{maintain_docs.KIND_TABLE_END}\n",
    )

    rendered = kind_index_after_writing(monkeypatch, tmp_path, ours, theirs)

    assert "<<<<<<<" not in rendered
    assert "=======" not in rendered
    assert rendered.startswith(
        "---\nstatus: living\ndate: 2026-09-02\n---\n\n# Research"
    )
    assert check_kinds(monkeypatch, tmp_path, ours, theirs) == []


def test_writing_the_indexes_satisfies_the_kind_index_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The flag the failure names is the remedy, so it has to produce a pass."""
    note = write_kind_document(tmp_path, "note.md", "A note")
    index = write_kind_index(tmp_path)
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(maintain_docs, "tracked_markdown_files", lambda: [note, index])
    (tmp_path / maintain_docs.ADR_DIRECTORY).mkdir(parents=True)
    monkeypatch.setattr(maintain_docs, "tracked_python_files", list)

    assert maintain_docs.main(["--write-indexes"]) == 0
    assert maintain_docs.check_kind_indexes([note, index]) == []


def test_writing_reports_a_kind_index_it_cannot_write_and_writes_the_rest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An index without markers is left alone and fails the run, without stopping the others."""
    note = write_kind_document(tmp_path, "note.md", "A note")
    unmarked = write_document(
        tmp_path, f"{KIND}/README.md", "---\nstatus: living\ndate: 2026-08-26\n---\n"
    )
    review = write_document(
        tmp_path,
        "docs/reviews/audit.md",
        "---\nstatus: research\ndate: 2026-08-26\n---\n\n# An audit\n",
    )
    write_document(
        tmp_path,
        "docs/reviews/README.md",
        f"# Reviews\n\n{maintain_docs.KIND_TABLE_START}\n{maintain_docs.KIND_TABLE_END}\n",
    )
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        maintain_docs, "tracked_markdown_files", lambda: [note, unmarked, review]
    )
    (tmp_path / maintain_docs.ADR_DIRECTORY).mkdir(parents=True)
    monkeypatch.setattr(maintain_docs, "tracked_python_files", list)

    assert maintain_docs.main(["--write-indexes"]) == 1
    assert "docs/research/README.md:1: marks no generated table" in (
        capsys.readouterr().err
    )
    assert unmarked.read_text(encoding="utf-8") == (
        "---\nstatus: living\ndate: 2026-08-26\n---\n"
    )
    assert "| [An audit](audit.md) |" in (
        tmp_path / "docs/reviews/README.md"
    ).read_text(encoding="utf-8")
    assert (tmp_path / maintain_docs.ADR_INDEX_PATH).is_file()


def test_writing_leaves_an_index_it_cannot_title_and_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty link would only trade the write's success for the gate's failure."""
    note = write_kind_document(tmp_path, "note.md", "")
    index = write_kind_index(tmp_path)
    committed = index.read_text(encoding="utf-8")
    adr = write_adr(tmp_path, "docs/adr/0001-first.md", "")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        maintain_docs, "tracked_markdown_files", lambda: [note, index, adr]
    )
    monkeypatch.setattr(maintain_docs, "tracked_python_files", list)

    assert maintain_docs.main(["--write-indexes"]) == 1
    assert capsys.readouterr().err.splitlines() == [
        "docs/adr/0001-first.md:1: declares no level-one heading, "
        "so the ADR index cannot title it",
        "docs/research/note.md:1: declares no level-one heading, "
        "so its kind index cannot title it",
    ]
    assert index.read_text(encoding="utf-8") == committed
    assert not (tmp_path / maintain_docs.ADR_INDEX_PATH).exists()


def ship(root: Path, *names: str, body: str = '"""A module."""\n') -> list[str]:
    """Write package files into a disposable tree and name them as Git lists them."""
    for name in names:
        write_document(root, f"src/dashpot/{name}", body)
    return [f"src/dashpot/{name}" for name in names]


def check_map(
    monkeypatch: pytest.MonkeyPatch, root: Path, shipped: list[str], body: str
) -> list[str]:
    """Run the code map gate over a disposable map and package."""
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", root)
    write_document(root, "docs/code-map.md", body)
    return [problem.render() for problem in maintain_docs.check_code_map(shipped)]


def test_a_code_map_listing_every_shipped_module_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A link is resolved as the link gate resolves it; links leaving the package do not count."""
    shipped = ship(tmp_path, "hook.py", "core/git.py")

    messages = check_map(
        monkeypatch,
        tmp_path,
        shipped,
        "| [`hook.py`](../src/dashpot/hook.py) | Publish. |\n"
        "| [`core/git.py`](../src/dashpot/core/../core/git%2Epy?plain=1#L1) | Run Git. |\n"
        "See [the design](design.md) and [AGENTS.md](../AGENTS.md#code-conventions).\n"
        "[Upstream](https://example.invalid/src/dashpot/gone.py) and [up](#code-map).\n",
    )

    assert messages == []


def test_a_shipped_module_the_code_map_leaves_out_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A new module has to be placed under its concept in the change that adds it."""
    shipped = ship(tmp_path, "hook.py", "core/git.py")

    messages = check_map(
        monkeypatch, tmp_path, shipped, "[`hook.py`](../src/dashpot/hook.py)\n"
    )

    assert messages == [
        "docs/code-map.md:1: does not list src/dashpot/core/git.py; "
        "add it under the concept it serves"
    ]


def test_a_code_map_link_to_a_module_not_shipped_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A removed module must not linger on the map, even while its file is on disk."""
    shipped = ship(tmp_path, "hook.py")
    write_document(tmp_path, "src/dashpot/untracked.py", "")

    messages = check_map(
        monkeypatch,
        tmp_path,
        shipped,
        "[`hook.py`](../src/dashpot/hook.py)\n\n"
        "[`gone.py`](../src/dashpot/gone.py)\n"
        "[`untracked.py`](../src/dashpot/untracked.py)\n",
    )

    assert messages == [
        "docs/code-map.md:3: links src/dashpot/gone.py, "
        "which the package does not ship",
        "docs/code-map.md:4: links src/dashpot/untracked.py, "
        "which the package does not ship",
    ]


def test_only_an_initializer_with_content_needs_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty initializer holds nothing to find; one that exports a seam does."""
    shipped = ship(tmp_path, "core/__init__.py", body="") + ship(
        tmp_path, "cleanup/__init__.py", body="from .perform import run as run\n"
    )

    messages = check_map(monkeypatch, tmp_path, shipped, "# Code map\n")

    assert messages == [
        "docs/code-map.md:1: does not list src/dashpot/cleanup/__init__.py; "
        "add it under the concept it serves"
    ]


def test_a_directory_lists_its_assets_but_never_its_modules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A bundled skill is one asset; a package link must not hide a module's absence."""
    shipped = ship(
        tmp_path,
        "skills/issue-work/SKILL.md",
        "skills/issue-work/references/dispatch.md",
        "sessions/work.py",
    )

    messages = check_map(
        monkeypatch,
        tmp_path,
        shipped,
        "[`skills/issue-work/`](../src/dashpot/skills/issue-work/)\n"
        "[`sessions/`](../src/dashpot/sessions/)\n",
    )

    assert messages == [
        "docs/code-map.md:1: does not list src/dashpot/sessions/work.py; "
        "add it under the concept it serves"
    ]


def test_links_in_code_do_not_list_a_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The map is read the way the link gate reads it, so an example is not an entry."""
    shipped = ship(tmp_path, "hook.py")

    messages = check_map(
        monkeypatch,
        tmp_path,
        shipped,
        "```markdown\n[`hook.py`](../src/dashpot/hook.py)\n```\n",
    )

    assert messages == [
        "docs/code-map.md:1: does not list src/dashpot/hook.py; "
        "add it under the concept it serves"
    ]


def test_a_commented_out_listing_does_not_list_a_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A link no reader sees lists nothing, and a stale one in a comment is no failure."""
    shipped = ship(tmp_path, "hook.py")

    messages = check_map(
        monkeypatch,
        tmp_path,
        shipped,
        "<!--\n| [`hook.py`](../src/dashpot/hook.py) | Publish. |\n"
        "| [`gone.py`](../src/dashpot/gone.py) | Removed. |\n-->\n",
    )

    assert messages == [
        "docs/code-map.md:1: does not list src/dashpot/hook.py; "
        "add it under the concept it serves"
    ]


def test_a_missing_code_map_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no map at all, every shipped module is unlisted; the gate says why once."""
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)

    problems = maintain_docs.check_code_map(ship(tmp_path, "hook.py"))

    assert [problem.render() for problem in problems] == [
        "docs/code-map.md:1: the code map is missing"
    ]


def test_the_shipped_files_are_what_git_tracks_in_the_package() -> None:
    """The map covers what the wheel ships, which is every tracked package file."""
    shipped = maintain_docs.tracked_package_files()

    assert "src/dashpot/hook.py" in shipped
    assert "src/dashpot/dashpot.tcss" in shipped
    assert all(name.startswith("src/dashpot/") for name in shipped)
    assert not any("__pycache__" in name for name in shipped)


def test_the_repository_documents_pass_every_gate() -> None:
    """Guard the real tree, so a stale link, status, ADR number, index or code map fails here too."""
    assert maintain_docs.main([]) == 0
