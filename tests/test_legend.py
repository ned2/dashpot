"""The Legend is derived from the Glyphs the panes render, and misses none."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import dashpot
from dashpot import alerts, branch_list, issue_cells, legend, session_list
from dashpot.alerts import AlertSeverity
from dashpot.glyphs import Glyph, LegendSection
from dashpot.issue_cells import IssueStateKind
from dashpot.model import RunState

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

    assert set(session_list.STATE_GLYPHS) == set(get_args(RunState))
    assert set(issue_cells.AGENT_STATE_GLYPHS) == set(get_args(RunState))
    assert set(issue_cells.ISSUE_STATE_GLYPHS) == set(get_args(IssueStateKind))
    assert set(alerts.SEVERITY_GLYPH) == set(get_args(AlertSeverity))
    for mapping in (
        session_list.STATE_GLYPHS,
        issue_cells.AGENT_STATE_GLYPHS,
        issue_cells.ISSUE_STATE_GLYPHS,
        issue_cells.SORT_GLYPHS,
        alerts.SEVERITY_GLYPH,
    ):
        assert {glyph.symbol for glyph in mapping.values()} <= symbols
    assert {glyph.symbol for glyph in branch_list.LEGEND} <= symbols
    assert issue_cells.ISSUE_STATE_COLUMN_GLYPH.symbol in symbols
    assert issue_cells.AGENT_STATE_COLUMN_GLYPH.symbol in symbols


def test_a_symbol_carries_one_meaning() -> None:
    meanings: dict[str, set[str]] = {}
    for glyph in legend.legend_glyphs():
        meanings.setdefault(glyph.symbol, set()).add(glyph.meaning)

    # The Issue state block differs by colour alone; every other symbol
    # means one thing wherever it is seen.
    collisions = {
        symbol: found
        for symbol, found in meanings.items()
        if len(found) > 1 and symbol != issue_cells.ISSUE_STATE_GLYPHS["open"].symbol
    }
    assert collisions == {}
    assert session_list.STATE_GLYPHS["unknown"].symbol != (
        branch_list.NO_UPSTREAM_GLYPH.symbol
    )


def test_legend_follows_the_screen_top_to_bottom() -> None:
    panes = [section.pane for section in legend.LEGEND]
    order = [
        "SESSIONS",
        "BRANCHES",
        "WORKTREES",
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


def test_remote_presence_is_qualified_as_the_last_fetch() -> None:
    """A REMOTE check is the Remote-Tracking Branch, never live remote presence."""
    by_column = {
        section.column: section
        for section in legend.LEGEND
        if section.pane == "BRANCHES"
    }
    local, remote = by_column["LOCAL"], by_column["REMOTE"]

    assert local.glyphs == remote.glyphs == branch_list.PRESENCE_LEGEND
    assert local.note == legend.LOCAL_PRESENCE_NOTE
    assert remote.note == legend.REMOTE_PRESENCE_NOTE
    rendered = legend.section_text(remote, dark=False).plain
    assert "Remote-Tracking Branch" in rendered
    assert "last fetch" in rendered
    assert "f fetches and prunes" in rendered


def test_section_text_renders_symbols_in_their_colour() -> None:
    section = legend.LEGEND[0]
    text = legend.section_text(section, dark=True)
    lines = text.plain.splitlines()

    assert lines[0].startswith(session_list.STATE_GLYPHS["running"].symbol)
    assert lines[0].endswith(session_list.STATE_GLYPHS["running"].meaning)
    assert str(text.spans[0].style) == session_list.STATE_GLYPHS["running"].style(
        dark=True
    )

    severity = legend.LEGEND[-1]
    themed = legend.section_text(severity, dark=True, theme={"error": "#ff0000"})
    assert str(themed.spans[0].style) == "#ff0000"
