"""The Issue table's rows, columns, cells and sorting, without an App."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app_harness import (
    issue,
    issue_metadata_text,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.issue_cells import (
    AGENT_STATE_COLUMN_GLYPH,
    ISSUE_STATE_COLUMN_GLYPH,
    IssueNumberCell,
    IssueStateCell,
    LabelsCell,
    PriorityCell,
    agent_state_cell,
    date_cell,
)
from dashpot.issue_list import query_issue_list, row_key
from dashpot.issue_table import (
    COLUMNS_BY_KEY,
    DEFAULT_COLUMNS,
    ColumnKey,
    IssueTableViewState,
    SortTerm,
    build_rows,
    searchable_columns,
    shown_columns,
    sort_key_for_terms,
)
from dashpot.local_markdown_issues import parse_local_markdown_issue
from dashpot.model import AgentRun, IssueActivity, LinkedPullRequest
from helpers import required, snapshot_of

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

ROOT = Path(__file__).resolve().parents[1]


def column_sort_key(column: ColumnKey) -> Callable[[object], SupportsRichComparison]:
    """A column's own ordering, for cells that all carry a sort value."""
    spec = COLUMNS_BY_KEY[column]
    return lambda cell: required(spec.sort_key(cell))


def test_row_projection_respects_visible_column_order() -> None:
    selected_issue = issue(
        "test/repo#1",
        "First",
        assignees=["ned2"],
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("title", "assignees", "project"),
    )

    selected_key = row_key("issue", selected_issue.id)
    assert set(contexts) == {selected_key}
    assert cells[selected_key] == ("First", "ned2", "Test Repository")


def test_author_column_is_hidden_by_default_and_sorts_missing_authors_last() -> None:
    authored = issue("test/repo#1", "Authored")
    anonymous = issue(
        "test/repo#2",
        "Anonymous",
        author=None,
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(authored, anonymous)),
        columns=("author",),
    )

    assert "author" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", authored.id)] == ("ned2",)
    assert cells[row_key("issue", anonymous.id)] == ("-",)
    values = [
        cells[row_key("issue", anonymous.id)][0],
        cells[row_key("issue", authored.id)][0],
    ]
    ascending = sorted(values, key=sort_key_for_terms((SortTerm("author"),)))
    assert [str(value) for value in ascending] == ["ned2", "-"]


def test_milestone_and_type_columns_are_hidden_by_default_and_optional() -> None:
    classified = issue("test/repo#1", "Classified")
    plain = issue(
        "test/repo#2",
        "Plain",
        milestone=None,
        issueType=None,
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(classified, plain)),
        columns=("milestone", "type"),
    )

    assert "milestone" not in DEFAULT_COLUMNS
    assert "type" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", classified.id)] == ("v1", "Feature")
    assert cells[row_key("issue", plain.id)] == ("-", "-")
    ascending = sorted(
        [
            cells[row_key("issue", plain.id)][0],
            cells[row_key("issue", classified.id)][0],
        ],
        key=sort_key_for_terms((SortTerm("milestone"),)),
    )
    assert [str(value) for value in ascending] == ["v1", "-"]


def test_comments_column_shows_engagement_only_when_present() -> None:
    discussed = issue("test/repo#1", "Discussed")
    quiet = issue("test/repo#2", "Quiet")
    snapshot = with_first_project_snapshot(
        workspace_snapshot(discussed, quiet),
        issue_activity={
            discussed.id: IssueActivity(
                comment_count=4,
                linked_pull_requests=[
                    LinkedPullRequest(
                        number=12,
                        url="https://github.com/test/repo/pull/12",
                        state="open",
                    ),
                    LinkedPullRequest(
                        number=41,
                        url="https://github.com/test/repo/pull/41",
                        state="merged",
                    ),
                ],
            )
        },
    )

    contexts, cells = build_rows(query_issue_list(snapshot), columns=("comments",))

    assert "comments" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", discussed.id)] == ("4",)
    assert cells[row_key("issue", quiet.id)] == ("-",)
    ascending = sorted(
        [
            cells[row_key("issue", discussed.id)][0],
            cells[row_key("issue", quiet.id)][0],
        ],
        key=sort_key_for_terms((SortTerm("comments"),)),
    )
    assert [str(value) for value in ascending] == ["-", "4"]

    detail = issue_metadata_text(contexts[row_key("issue", discussed.id)])
    assert "Comments: 4\n" in detail
    assert (
        "Pull requests:\n"
        "  #12 open https://github.com/test/repo/pull/12\n"
        "  #41 merged https://github.com/test/repo/pull/41\n"
        "Relationships:"
    ) in detail

    quiet_detail = issue_metadata_text(contexts[row_key("issue", quiet.id)])
    assert "Comments: 0\n" in quiet_detail
    assert "Pull requests:\n  -\n" in quiet_detail


def test_issue_number_column_uses_the_bare_project_local_number() -> None:
    selected_issue = issue("test/repo#17", "Reference test")

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("number",),
    )

    number = cells[row_key("issue", selected_issue.id)][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_issue_date_columns_render_iso_dates_and_sort_by_full_timestamp() -> None:
    selected_issue = issue(
        "test/repo#17",
        "Timestamp test",
        createdAt="2026-08-25T23:30:00Z",
        updatedAt="2026-08-27T01:15:00Z",
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(selected_issue)),
        columns=("created", "last_action"),
    )

    assert cells[row_key("issue", selected_issue.id)] == (
        "2026-08-25",
        "2026-08-27",
    )
    timestamps = [
        date_cell(None),
        date_cell("2026-08-27T01:15:00Z"),
        date_cell("2026-08-27T00:30:00Z"),
    ]
    ascending = sorted(
        timestamps,
        key=sort_key_for_terms((SortTerm("last_action"),)),
    )
    descending = sorted(
        timestamps,
        key=sort_key_for_terms((SortTerm("last_action", descending=True),)),
        reverse=True,
    )
    assert ascending[0] is timestamps[2]
    assert ascending[1] is timestamps[1]
    assert ascending[2] is timestamps[0]
    assert descending[0] is timestamps[1]
    assert descending[1] is timestamps[2]
    assert descending[2] is timestamps[0]


def test_labels_column_renders_tracker_coloured_chips_and_sorts_by_name() -> None:
    labelled = issue(
        "test/repo#1",
        "Labelled",
        labels=["bug", "enhancement", "zeta"],
    )
    bare = issue(
        "test/repo#2",
        "Bare",
        labels=[],
    )
    snapshot = with_first_project_snapshot(
        workspace_snapshot(labelled, bare),
        label_colors={"bug": "d73a4a", "enhancement": "a2eeef"},
    )

    _contexts, cells = build_rows(query_issue_list(snapshot), columns=("labels",))

    chips = cells[row_key("issue", labelled.id)][0]
    assert isinstance(chips, LabelsCell)
    assert chips.plain == " bug   enhancement   zeta "
    assert chips.sort_value == ("bug", "enhancement", "zeta")
    styles = [str(span.style) for span in chips.spans]
    assert styles == [
        "#ffffff on #d73a4a",
        "#000000 on #a2eeef",
        "#ffffff on #6e7781",
    ]
    empty = cells[row_key("issue", bare.id)][0]
    assert isinstance(empty, LabelsCell)
    assert empty.plain == "-"
    assert empty.sort_value is None

    ascending = sorted([empty, chips], key=sort_key_for_terms((SortTerm("labels"),)))
    assert ascending == [chips, empty]
    descending = sorted(
        [empty, chips],
        key=sort_key_for_terms((SortTerm("labels", descending=True),)),
        reverse=True,
    )
    assert descending == [chips, empty]


def test_priority_column_is_a_chip_in_its_source_label_colour() -> None:
    # The most urgent recognized label sets the priority and lends its colour.
    urgent = issue(
        "test/repo#1", "Urgent", labels=["bug", "priority/p3", "priority/P0"]
    )
    routine = issue(
        "test/repo#2",
        "Routine",
        labels=["low"],
    )
    snapshot = with_first_project_snapshot(
        workspace_snapshot(urgent, routine),
        label_colors={
            "bug": "d73a4a",
            "priority/P0": "b60205",
            "priority/p3": "0e8a16",
        },
    )
    result = query_issue_list(snapshot)

    assert "priority" in DEFAULT_COLUMNS
    assert shown_columns(DEFAULT_COLUMNS, result.rows) == DEFAULT_COLUMNS
    for dark in (True, False):
        _contexts, cells = build_rows(result, columns=("priority", "labels"), dark=dark)

        priority, labels = cells[row_key("issue", urgent.id)]
        assert isinstance(priority, PriorityCell)
        assert priority.plain == " P0 "
        assert priority.priority == "P0"
        assert priority.sort_value == 0
        assert [str(span.style) for span in priority.spans] == ["#ffffff on #b60205"]
        # The priority labels leave the LABELS chips rather than render twice.
        assert isinstance(labels, LabelsCell)
        assert labels.labels == ("bug",)
        assert labels.plain == " bug "
        low, bare = cells[row_key("issue", routine.id)]
        assert isinstance(low, PriorityCell)
        assert low.plain == " P3 "
        assert [str(span.style) for span in low.spans] == ["#ffffff on #6e7781"]
        assert isinstance(bare, LabelsCell)
        assert bare.plain == "-"


def test_priority_column_shows_only_while_some_issue_carries_a_priority_label() -> None:
    prioritised = issue("test/repo#1", "Prioritised", "P1")
    unlabelled = issue(
        "test/repo#2",
        "Unlabelled",
        labels=["bug"],
    )
    without_priority = tuple(key for key in DEFAULT_COLUMNS if key != "priority")

    mixed = query_issue_list(workspace_snapshot(prioritised, unlabelled))
    assert shown_columns(DEFAULT_COLUMNS, mixed.rows) == DEFAULT_COLUMNS
    for descending in (False, True):
        _contexts, cells = build_rows(
            mixed,
            columns=("priority",),
            sort=(SortTerm("priority", descending=descending),),
        )
        # An Issue without a priority label shows nothing and sorts after
        # every priority in either direction: no default is invented.
        absent = cells[row_key("issue", unlabelled.id)][0]
        assert isinstance(absent, PriorityCell)
        assert absent.plain == ""
        assert absent.priority is None
        assert absent.sort_value is None
        assert list(cells) == [
            row_key("issue", prioritised.id),
            row_key("issue", unlabelled.id),
        ]

    plain = query_issue_list(workspace_snapshot(unlabelled))
    assert shown_columns(DEFAULT_COLUMNS, plain.rows) == without_priority
    assert shown_columns(DEFAULT_COLUMNS, ()) == without_priority
    assert shown_columns(("title", "labels"), plain.rows) == ("title", "labels")


def test_local_markdown_number_is_the_table_id() -> None:
    document = (
        ROOT / "tests" / "fixtures" / "local-markdown" / "ISSUES.md"
    ).read_text()
    document = (
        document.replace('"id": "I_kwDOUEerrs8AAAABOSTptQ"', '"id": "I_local_17"')
        .replace('"number": 9', '"number": 17')
        .replace('"reference": "ned2/dashpot#9"', '"reference": "local-17"')
    )
    local_issue = parse_local_markdown_issue(
        document,
        project_id="project:test-repo",
        path="issues/local-17.md",
    )

    _contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(local_issue)),
        columns=("number",),
    )

    number = cells[row_key("issue", "I_local_17")][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_selecting_a_sort_column_replaces_the_default_then_toggles_direction() -> None:
    view = IssueTableViewState()

    ascending = view.toggle_sort("number")
    descending = ascending.toggle_sort("number")

    assert ascending.sort == (SortTerm("number"),)
    assert descending.sort == (SortTerm("number", descending=True),)


def test_icon_and_title_columns_are_not_sortable() -> None:
    view = IssueTableViewState(
        columns=("issue_state", "agent_state", "title", "number", "priority"),
        sort=(SortTerm("title"),),
    )

    assert view.toggle_sort("issue_state") is view
    assert view.toggle_sort("agent_state") is view
    assert view.toggle_sort("title") is view
    # From an unsortable current column, cycling continues from its catalogue
    # position: priority follows title, then wraps back to number.
    assert view.cycle_sort().sort == (SortTerm("priority"),)
    assert view.cycle_sort().cycle_sort().sort == (SortTerm("number"),)
    icon_only = IssueTableViewState(
        columns=("issue_state", "agent_state", "title"),
        sort=(),
    )
    assert icon_only.cycle_sort() is icon_only
    assert icon_only.reverse_sort() is icon_only


def test_table_view_rejects_empty_or_duplicate_column_layouts() -> None:
    view = IssueTableViewState()

    with pytest.raises(ValueError, match="at least one"):
        view.with_columns(())
    with pytest.raises(ValueError, match="duplicates"):
        view.with_columns(("title", "title"))


def test_column_catalogue_owns_searchability_and_typed_sort_keys() -> None:
    assert searchable_columns() == frozenset(
        {
            "number",
            "project",
            "assignees",
            "labels",
            "author",
            "milestone",
            "type",
            "title",
        }
    )
    agent_states = [
        agent_state_cell(("running",)),
        agent_state_cell(()),
        agent_state_cell(("waiting",)),
        agent_state_cell(("unknown",)),
    ]

    ordered = sorted(agent_states, key=column_sort_key("agent_state"))

    assert ordered == ["", "?", "Ⅱ", "▶"]
    assert agent_state_cell(("running", "running")) == "▶"
    assert agent_state_cell(("waiting", "running", "unknown")) == "▶"
    assert agent_state_cell(("unknown", "waiting")) == "Ⅱ"
    numbers = [IssueNumberCell(10), IssueNumberCell(2)]

    assert sorted(numbers, key=column_sort_key("number")) == [
        IssueNumberCell(2),
        IssueNumberCell(10),
    ]
    assert all(number.justify == "right" for number in numbers)
    states = [
        IssueStateCell("duplicate", dark=True),
        IssueStateCell("open", dark=True),
        IssueStateCell("not-planned", dark=True),
        IssueStateCell("completed", dark=True),
    ]

    assert [
        cell.state_kind for cell in sorted(states, key=column_sort_key("issue_state"))
    ] == ["open", "completed", "not-planned", "duplicate"]


def test_correlated_run_state_is_visible_in_queue_and_detail() -> None:
    selected_issue = issue(
        "test/repo#1",
        "First",
        assignees=["ned2"],
    )
    run = AgentRun(
        id="codex-session:42",
        harness="codex",
        process_or_session="42",
        state="waiting",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/1",
        issue_id=selected_issue.id,
        issue_reference_hint=selected_issue.reference,
    )
    snapshot = workspace_snapshot(selected_issue, runs=[run])
    snapshot = snapshot.model_copy(
        update={"issue_runs": {**snapshot.issue_runs, selected_issue.id: (run.id,)}}
    )

    contexts, cells = build_rows(query_issue_list(snapshot))

    selected_key = row_key("issue", selected_issue.id)
    assert len(cells[selected_key]) == len(DEFAULT_COLUMNS) == 7
    number_cell = cells[selected_key][DEFAULT_COLUMNS.index("number")]
    assert str(number_cell) == "1"
    assert isinstance(number_cell, IssueNumberCell)
    assert number_cell.justify == "right"
    assert cells[selected_key][DEFAULT_COLUMNS.index("agent_state")] == "Ⅱ"
    detail = issue_metadata_text(contexts[selected_key])
    assert "Assignees: ned2" in detail
    assert "codex-session:42 (waiting, issue/1)" in detail


def test_duplicate_issue_identities_get_distinct_project_qualified_rows() -> None:
    duplicated = issue("test/repo#1", "First")
    snapshot = workspace_snapshot(duplicated)
    other_identity = {
        "project_id": "project:other-repo",
        "display_label": "Other Repository",
        "repository_id": "repository:other-repo",
    }
    second = snapshot.projects[0].model_copy(
        update={
            **other_identity,
            "snapshot": snapshot_of(snapshot.projects[0]).model_copy(
                update=other_identity
            ),
        }
    )
    snapshot = snapshot.model_copy(update={"projects": (*snapshot.projects, second)})

    contexts, cells = build_rows(query_issue_list(snapshot))

    expected = {
        row_key("issue", "project:test-repo", duplicated.id),
        row_key("issue", "project:other-repo", duplicated.id),
    }
    assert set(cells) == expected
    assert set(contexts) == expected
    assert {context.project.project_id for context in contexts.values()} == {
        "project:test-repo",
        "project:other-repo",
    }


def test_default_issue_filter_shows_only_open_issues() -> None:
    open_issue = issue("test/repo#1", "Open")
    closed_issue = issue(
        "test/repo#2",
        "Closed",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
    )

    contexts, cells = build_rows(
        query_issue_list(workspace_snapshot(open_issue, closed_issue))
    )

    assert set(contexts) == set(cells) == {row_key("issue", open_issue.id)}
    assert (
        cells[row_key("issue", open_issue.id)][DEFAULT_COLUMNS.index("title")] == "Open"
    )


def test_project_with_only_closed_issues_has_no_open_issues_row() -> None:
    closed_issue = issue(
        "test/repo#2",
        "Closed",
        state="closed",
        stateReason="completed",
        closedAt="2026-08-27T01:00:00Z",
    )

    contexts, cells = build_rows(query_issue_list(workspace_snapshot(closed_issue)))

    assert contexts == {}
    assert cells == {}


def test_glyph_header_tooltips_are_the_meanings_the_legend_shows() -> None:
    assert COLUMNS_BY_KEY["issue_state"].tooltip == ISSUE_STATE_COLUMN_GLYPH.meaning
    assert COLUMNS_BY_KEY["agent_state"].tooltip == AGENT_STATE_COLUMN_GLYPH.meaning
    assert {key for key, spec in COLUMNS_BY_KEY.items() if spec.tooltip} == {
        "issue_state",
        "agent_state",
    }
