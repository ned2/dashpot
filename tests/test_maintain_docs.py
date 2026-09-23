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
    monkeypatch.setattr(maintain_docs, "tracked_markdown_files", list)

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
        "regenerate it with --write-adr-index"
    ]


def test_a_missing_index_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A repository with ADRs and no index is as out of date as a stale one."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)

    problems = maintain_docs.check_adr_index([first])

    assert [problem.render() for problem in problems] == [
        "docs/adr/README.md:1: the ADR index is missing; "
        "regenerate it with --write-adr-index"
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


def test_writing_the_index_satisfies_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The write path is the remedy both failures name, so it has to produce a pass."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    second = write_adr(tmp_path, "docs/adr/0002-second.md", "Do the second thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        maintain_docs, "tracked_markdown_files", lambda: [first, second]
    )

    assert maintain_docs.main(["--write-adr-index"]) == 0
    assert maintain_docs.check_adr_index([first, second]) == []


def test_writing_the_index_still_rejects_an_untracked_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A typo must not be swallowed by the flag that ignores the selection."""
    first = write_adr(tmp_path, "docs/adr/0001-first.md", "Do the first thing")
    monkeypatch.setattr(maintain_docs, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(maintain_docs, "tracked_markdown_files", lambda: [first])

    assert maintain_docs.main(["--write-adr-index", "docs/does-not-exist.md"]) == 1
    assert not (tmp_path / maintain_docs.ADR_INDEX_PATH).exists()


def test_the_repository_documents_pass_every_gate() -> None:
    """Guard the real tree, so a stale link, status, ADR number, or index fails here too."""
    assert maintain_docs.main([]) == 0
