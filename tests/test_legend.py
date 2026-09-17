"""The Legend is derived from the Glyphs the panes render, and misses none."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import dashpot
from dashpot.core.model import RunState
from dashpot.ui import alerts, branch_cells, glyphs, issue_cells, legend, session_cells
from dashpot.ui.alerts import AlertSeverity
from dashpot.ui.glyphs import Glyph, LegendSection
from dashpot.ui.issue_cells import IssueStateKind
from dashpot.ui.list_rows import ListColumn, column_help
from helpers import required

SOURCE_DIR = Path(dashpot.__file__).parent
# Typography that never stands for a fact: separators, clipping, and prose.
PUNCTUATION = frozenset("·…—→")


def legend_symbols() -> set[str]:
    return {glyph.symbol for glyph in legend.legend_glyphs()}


def test_glyph_style_follows_the_theme() -> None:
    coloured = Glyph("●", "running", ("#1a7f37", "#3fb950"))
    themed = Glyph("✖", "error", theme_color="error")
    plain = Glyph("✓", "in sync")

    assert coloured.style(dark=False) == "#1a7f37"
    assert coloured.style(dark=True) == "#3fb950"
    assert themed.style(dark=True) == ""
    assert themed.style(dark=True, theme={"error": "#ff0000"}) == "#ff0000"
    assert plain.style(dark=True, theme={"error": "#ff0000"}) == ""


def test_every_rendered_glyph_map_is_in_the_legend() -> None:
    symbols = legend_symbols()

    assert set(session_cells.STATE_GLYPHS) == set(get_args(RunState))
    assert set(issue_cells.AGENT_STATE_GLYPHS) == set(get_args(RunState))
    assert set(issue_cells.ISSUE_STATE_GLYPHS) == set(get_args(IssueStateKind))
    assert set(alerts.SEVERITY_GLYPH) == set(get_args(AlertSeverity))
    for mapping in (
        session_cells.STATE_GLYPHS,
        issue_cells.AGENT_STATE_GLYPHS,
        issue_cells.ISSUE_STATE_GLYPHS,
        issue_cells.SORT_GLYPHS,
        alerts.SEVERITY_GLYPH,
    ):
        assert {glyph.symbol for glyph in mapping.values()} <= symbols
    assert {glyph.symbol for glyph in branch_cells.LEGEND} <= symbols
    assert issue_cells.ISSUE_STATE_COLUMN_GLYPH.symbol in symbols
    assert issue_cells.AGENT_STATE_COLUMN_GLYPH.symbol in symbols


def test_a_symbol_carries_one_meaning() -> None:
    meanings: dict[str, set[str]] = {}
    for glyph in legend.legend_glyphs():
        meanings.setdefault(glyph.symbol, set()).add(glyph.meaning)

    # Issue and Pull Request state blocks share colour encoding, and the
    # Branches INTEGRATED cell's ↑ (work above the Integration Branch) is
    # the Issues header sort marker's ↑ read on a different surface; every
    # other symbol means one thing wherever it is seen.
    shared = {
        issue_cells.ISSUE_STATE_GLYPHS["open"].symbol,
        branch_cells.UNINTEGRATED_GLYPH.symbol,
    }
    assert (
        branch_cells.UNINTEGRATED_GLYPH.symbol == issue_cells.SORT_GLYPHS[False].symbol
    )
    collisions = {
        symbol: found
        for symbol, found in meanings.items()
        if len(found) > 1 and symbol not in shared
    }
    assert collisions == {}
    assert session_cells.STATE_GLYPHS["unknown"].symbol != (
        branch_cells.NO_UPSTREAM_GLYPH.symbol
    )


def test_legend_follows_the_screen_top_to_bottom() -> None:
    panes = [section.pane for section in legend.LEGEND]
    order = [
        "SESSIONS",
        "WORKTREES",
        "BRANCHES",
        "PULL REQUESTS",
        "ISSUES",
        legend.DIAGNOSTICS_LABEL,
    ]

    assert [pane for pane in order if pane in panes] == order
    assert panes == sorted(panes, key=order.index)
    assert all(isinstance(section, LegendSection) for section in legend.LEGEND)


def non_ascii_in_string_constants(path: Path) -> dict[str, set[str]]:
    """Every non-ASCII character in a rendered string, by ``file:line``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        for character in node.value:
            if ord(character) > 0x7F and character not in PUNCTUATION:
                found.setdefault(character, set()).add(f"{path.name}:{node.lineno}")
    return found


def test_every_glyph_in_the_source_is_explained() -> None:
    explained = {
        character
        for symbol in legend_symbols()
        for character in symbol
        if ord(character) > 0x7F
    }
    unexplained: dict[str, set[str]] = {}
    for path in sorted(SOURCE_DIR.glob("*.py")):
        for character, sites in non_ascii_in_string_constants(path).items():
            if character not in explained:
                unexplained.setdefault(character, set()).update(sites)

    assert unexplained == {}


def branches_sections() -> dict[str, LegendSection]:
    return {
        section.column: section
        for section in legend.LEGEND
        if section.pane == "BRANCHES"
    }


def test_every_branches_column_is_in_the_legend_from_its_own_definition() -> None:
    """The Legend's Branches sections are the pane's columns, tooltips included."""
    sections = [section for section in legend.LEGEND if section.pane == "BRANCHES"]

    assert [section.column for section in sections] == [
        column.label for column in branch_cells.BRANCH_COLUMNS
    ]
    for section, column in zip(sections, branch_cells.BRANCH_COLUMNS, strict=True):
        assert column.description
        assert section.note == column.description
        assert section.glyphs == column.glyphs
        # The header tooltip is the same description and the same Glyph
        # meanings, formatted for a mouse rather than the modal.
        help_text = column_help(column)
        assert help_text is not None
        assert help_text.startswith(column.description)
        for glyph in column.glyphs:
            assert glyph.symbol in help_text
            assert glyph.meaning in help_text
        rendered = legend.section_text(section, dark=False).plain
        assert rendered.endswith(column.description)
        for glyph in column.glyphs:
            assert glyph.meaning in rendered
    by_column = branches_sections()
    assert by_column["◈"].glyphs == glyphs.ACTIVITY_LEGEND
    assert by_column["LOCAL"].glyphs == branch_cells.PRESENCE_LEGEND
    assert by_column["UPSTREAM"].glyphs == branch_cells.UPSTREAM_LEGEND
    assert by_column["INTEGRATED"].glyphs == branch_cells.INTEGRATION_LEGEND
    # A column that renders no Glyph is its description alone.
    assert by_column["BRANCH"].glyphs == ()
    assert (
        legend.section_text(by_column["BRANCH"], dark=False).plain
        == branch_cells.NAME_DESCRIPTION
    )
    assert column_help(ListColumn("bare", "BARE")) is None


def test_remote_presence_is_qualified_as_the_last_fetch() -> None:
    """A REMOTE check is the Remote-Tracking Branch, never live remote presence."""
    by_column = branches_sections()
    local, remote = by_column["LOCAL"], by_column["REMOTE"]

    assert local.glyphs == remote.glyphs == branch_cells.PRESENCE_LEGEND
    assert local.note == branch_cells.LOCAL_DESCRIPTION
    assert remote.note == branch_cells.REMOTE_DESCRIPTION
    rendered = legend.section_text(remote, dark=False).plain
    assert "Remote-Tracking Branch" in rendered
    assert "last fetch" in rendered
    assert "f fetches and prunes" in rendered


def test_the_cleanup_gate_is_stated_where_x_reads_it() -> None:
    """The INTEGRATED and Worktree SESSIONS notes separate the row from x's checks."""
    sections = {(section.pane, section.column): section for section in legend.LEGEND}
    integrated = sections["BRANCHES", "INTEGRATED"]
    worktrees = sections["WORKTREES", "◈"]

    assert integrated.glyphs == branch_cells.INTEGRATION_LEGEND
    assert integrated.note == branch_cells.INTEGRATION_DESCRIPTION
    assert worktrees.note == legend.WORKTREE_SESSIONS_NOTE
    assert required(worktrees.note).startswith(legend.SESSIONS_COUNT_NOTE)
    for section, words in (
        (
            integrated,
            (
                "every ref this row represents",
                "each same-name Remote-Tracking Branch",
                "as of the last fetch",
                "not a differently named upstream",
                "Known unintegrated work outranks missing evidence",
                "never reads as integrated",
                "prerequisite for the Cleanup x opens",
                "not a verdict on its targets",
                "each target's own integration and commit count",
                "blockers, selection, and confirmation",
            ),
        ),
        (
            worktrees,
            (
                "x removes",
                "clean",
                "no Agent Session or Agent Run",
                "retains its Branch",
            ),
        ),
    ):
        rendered = legend.section_text(section, dark=False).plain
        for word in words:
            assert word in rendered


def test_section_text_renders_symbols_in_their_colour() -> None:
    section = legend.LEGEND[0]
    text = legend.section_text(section, dark=True)
    lines = text.plain.splitlines()

    assert lines[1].startswith(session_cells.STATE_GLYPHS["running"].symbol)
    assert lines[1].endswith(session_cells.STATE_GLYPHS["running"].meaning)
    assert str(text.spans[0].style) == session_cells.STATE_GLYPHS["running"].style(
        dark=True
    )

    severity = legend.LEGEND[-1]
    themed = legend.section_text(severity, dark=True, theme={"error": "#ff0000"})
    assert str(themed.spans[0].style) == "#ff0000"
