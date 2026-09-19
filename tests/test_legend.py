"""The Legend is derived from the panes' columns and Glyphs, and misses none."""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path
from typing import cast, get_args

import pytest
from textual.binding import Binding, BindingType

import dashpot
from dashpot.core.model import RunState
from dashpot.ui import (
    alerts,
    branch_cells,
    glyphs,
    issue_cells,
    issue_table,
    legend,
    pull_request_cells,
    session_cells,
    worktree_cells,
)
from dashpot.ui.alerts import AlertSeverity
from dashpot.ui.app import FOCUS_CYCLE_BINDINGS, legend_keys
from dashpot.ui.glyphs import Glyph, LegendSection
from dashpot.ui.issue_cells import IssueStateKind
from dashpot.ui.issue_table import COLUMN_SPECS, DEFAULT_COLUMNS
from dashpot.ui.list_pane import ISSUE_PANE_LABEL
from dashpot.ui.list_rows import DescribedColumn, ListColumn, column_help
from dashpot.ui.panes import LIST_PANE_SPECS
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
        legend.STATUS_BAR_LABEL,
        "SESSIONS",
        "WORKTREES",
        "BRANCHES",
        "PULL REQUESTS",
        "ISSUES",
        legend.RELATED_ROWS_LABEL,
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


def pane_sections(pane: str) -> list[LegendSection]:
    return [section for section in legend.LEGEND if section.pane == pane]


def branches_sections() -> dict[str, LegendSection]:
    return {section.column: section for section in pane_sections("BRANCHES")}


# Every pane's column catalogue, read from the pane specs the dashboard is
# composed from and the Issue table's own catalogue, so a column added to
# either is checked here without a list of labels to maintain.
COLUMN_INVENTORY: tuple[tuple[str, tuple[DescribedColumn, ...]], ...] = (
    *((spec.label, spec.columns) for spec in LIST_PANE_SPECS),
    (ISSUE_PANE_LABEL, COLUMN_SPECS),
)
# The sections that are not one column of the pane they sit under.
EXTRA_SECTIONS = {
    ("WORKTREES", legend.WORKTREE_ACTIONS_SECTION),
    (ISSUE_PANE_LABEL, legend.ISSUE_COLUMNS_SECTION),
}


@pytest.mark.parametrize(
    ("pane", "columns"), COLUMN_INVENTORY, ids=[pane for pane, _ in COLUMN_INVENTORY]
)
def test_every_column_is_in_the_legend_from_its_own_definition(
    pane: str, columns: tuple[DescribedColumn, ...]
) -> None:
    """Each pane's Legend sections are its columns, tooltips included.

    The Issue table's optional columns are listed whether or not they are
    shown, so the Legend explains what a column a person has not chosen
    would tell them.
    """
    sections = pane_sections(pane)
    labels = [column.label for column in columns]

    assert columns, pane
    assert [section.column for section in sections if section.column in labels] == (
        labels
    )
    assert {
        (section.pane, section.column)
        for section in sections
        if section.column not in labels
    } <= EXTRA_SECTIONS
    for section, column in zip(
        [section for section in sections if section.column in labels],
        columns,
        strict=True,
    ):
        assert column.description, (pane, column.label)
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


def test_the_branches_sections_carry_the_panes_glyph_vocabularies() -> None:
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


def test_the_activity_column_means_what_each_pane_shows() -> None:
    """One Glyph heads four columns, and each says which fact it summarizes."""
    sections = {(section.pane, section.column): section for section in legend.LEGEND}
    activity = [
        sections[pane, glyphs.ACTIVITY_COLUMN_GLYPH.symbol]
        for pane in ("SESSIONS", "WORKTREES", "BRANCHES", ISSUE_PANE_LABEL)
    ]
    notes = [required(section.note) for section in activity]

    # The Glyph meanings are the shared ones; the descriptions are not.
    assert all(section.glyphs == glyphs.ACTIVITY_LEGEND for section in activity)
    assert len(set(notes)) == len(notes)
    assert notes[0] == session_cells.STATE_DESCRIPTION
    assert "this Agent Session's own" in notes[0]
    assert notes[1] == worktree_cells.activity_description("at this Worktree")
    assert notes[2] == worktree_cells.activity_description("on this Branch")
    assert notes[3] == issue_table.AGENT_STATE_DESCRIPTION
    assert "the liveliest Agent Run explicitly bound" in notes[3]
    assert "Issue Binding" in notes[3]
    # The count column beside the located ones says where it counts too.
    assert sections["WORKTREES", "SESSIONS"].note == (
        worktree_cells.sessions_description("at this Worktree")
    )
    assert sections["BRANCHES", "SESSIONS"].note == (
        worktree_cells.sessions_description("on this Branch")
    )
    assert sections["SESSIONS", "ISSUE"].note == session_cells.ISSUE_DESCRIPTION
    assert "Issue Hint, not a binding" in session_cells.ISSUE_DESCRIPTION
    assert "turn boundaries" in session_cells.ACTIVITY_DESCRIPTION
    assert "running 14m" in session_cells.ACTIVITY_DESCRIPTION


def test_pull_request_observations_say_what_they_establish() -> None:
    sections = {section.column: section for section in pane_sections("PULL REQUESTS")}

    assert sections["STATE"].glyphs == pull_request_cells.STATE_LEGEND
    assert sections["REVIEW"].glyphs == pull_request_cells.REVIEW_LEGEND
    assert sections["CHECKS"].glyphs == pull_request_cells.CHECKS_LEGEND
    assert sections["MERGE"].glyphs == pull_request_cells.MERGE_LEGEND
    for column, words in (
        ("REVIEW", ("protection rules", "not whether the Pull Request may merge")),
        ("CHECKS", ("checks and commit statuses", "not a gate")),
        ("MERGE", ("without conflicts", "n/a for a closed or merged")),
        ("UPDATED", ("as of the page's query",)),
    ):
        rendered = legend.section_text(sections[column], dark=False).plain
        for word in words:
            assert word in rendered, column


def test_the_issue_columns_note_lists_the_optional_columns() -> None:
    section = next(
        section
        for section in pane_sections(ISSUE_PANE_LABEL)
        if section.column == legend.ISSUE_COLUMNS_SECTION
    )
    optional = [spec.label for spec in COLUMN_SPECS if spec.key not in DEFAULT_COLUMNS]

    assert section.glyphs == issue_cells.LEGEND_SORT
    assert optional
    assert ", ".join(optional) in required(section.note)
    assert "c chooses" in required(section.note)
    assert "PRIORITY" in required(section.note)


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
    """The INTEGRATED and Worktree actions notes separate a row from x's checks."""
    sections = {(section.pane, section.column): section for section in legend.LEGEND}
    integrated = sections["BRANCHES", "INTEGRATED"]
    worktrees = sections["WORKTREES", legend.WORKTREE_ACTIONS_SECTION]

    assert integrated.glyphs == branch_cells.INTEGRATION_LEGEND
    assert integrated.note == branch_cells.INTEGRATION_DESCRIPTION
    assert worktrees.glyphs == ()
    assert worktrees.note == legend.WORKTREE_ACTIONS_NOTE
    assert sections["WORKTREES", "TREE"].note == worktree_cells.TREE_DESCRIPTION
    assert "only a clean linked Worktree" in worktree_cells.TREE_DESCRIPTION
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
                "Enter opens",
                "y sends its full path",
            ),
        ),
    ):
        rendered = legend.section_text(section, dark=False).plain
        for word in words:
            assert word in rendered


def test_section_text_renders_symbols_in_their_colour() -> None:
    section = next(section for section in legend.LEGEND if section.pane == "SESSIONS")
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


def shipped_bindings() -> set[tuple[str, str]]:
    """Every shown ``(key, description)`` a class under ``dashpot.ui`` binds."""
    found: set[tuple[str, str]] = set()
    for module_info in pkgutil.iter_modules(
        [str(SOURCE_DIR / "ui")], prefix="dashpot.ui."
    ):
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if (
                not isinstance(value, type)
                or value.__module__ != module_info.name
                or "BINDINGS" not in vars(value)
            ):
                continue
            bindings = vars(value)["BINDINGS"]
            assert isinstance(bindings, list)
            found.update(
                (binding.key, binding.description)
                for binding in Binding.make_bindings(
                    cast("list[BindingType]", bindings)
                )
                if binding.show
            )
    return found


def test_the_legend_lists_every_shipped_key_and_the_focus_cycle() -> None:
    """A key on any screen or widget is explained, including Tab's override."""
    listed = {
        (binding.key, binding.description)
        for group in legend_keys()
        for binding in Binding.make_bindings(group.bindings)
    }
    shipped = shipped_bindings()

    assert shipped, "no shipped BINDINGS were found under dashpot.ui"
    assert shipped <= listed
    assert {
        (binding.key, binding.description)
        for binding in Binding.make_bindings(FOCUS_CYCLE_BINDINGS)
    } == {("tab", "Next list"), ("shift+tab", "Previous list")}
    assert ("tab", "Next list") in listed
    assert ("shift+tab", "Previous list") in listed
    # Each group is named for where its keys are pressed, and no key is
    # listed twice within its group.
    labels = [group.label for group in legend_keys()]
    assert len(set(labels)) == len(labels)
    for group in legend_keys():
        keys = [binding.key for binding in Binding.make_bindings(group.bindings)]
        assert len(set(keys)) == len(keys), group.label
