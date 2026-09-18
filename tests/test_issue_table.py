"""The Issue table's rows, columns and cells, without an App."""

from __future__ import annotations

from pathlib import Path

import pytest

from app_harness import (
    issue,
    issue_metadata_text,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.core.model import AgentRun, IssueActivity, LinkedPullRequest
from dashpot.issues.local_markdown_issues import parse_local_markdown_issue
from dashpot.observation.issue_list import row_key
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.ui.issue_cells import (
    AGENT_STATE_COLUMN_GLYPH,
    ISSUE_STATE_COLUMN_GLYPH,
    LEGEND_AGENT_STATE,
    LEGEND_ISSUE_STATE,
    IssueNumberCell,
    IssueStateCell,
    LabelsCell,
    PriorityCell,
    agent_state_cell,
    date_cell,
)
from dashpot.ui.issue_table import (
    COLUMN_SPECS,
    COLUMNS_BY_KEY,
    DEFAULT_COLUMNS,
    TITLE_LIMIT,
    IssueTableViewState,
    build_rows,
    searchable_columns,
    shown_columns,
)
from dashpot.ui.list_rows import column_help
from helpers import required, snapshot_of

ROOT = Path(__file__).resolve().parents[1]


def test_row_projection_respects_visible_column_order() -> None:
    selected_issue = issue(
        "test/repo#1",
        "First",
        assignees=["ned2"],
    )

    contexts, cells = build_rows(
        WorkspaceObservationStore(workspace_snapshot(selected_issue)).query_issues(),
        columns=("title", "assignees", "project"),
    )

    selected_key = row_key("issue", selected_issue.id)
    assert set(contexts) == {selected_key}
    assert cells[selected_key] == ("First", "ned2", "Test Repository")


def test_a_long_title_is_clipped_with_an_ellipsis_at_the_limit() -> None:
    long_title = "A title " + "x" * TITLE_LIMIT
    exact = issue("test/repo#1", "y" * TITLE_LIMIT)
    overlong = issue("test/repo#2", long_title)

    contexts, cells = build_rows(
        WorkspaceObservationStore(workspace_snapshot(exact, overlong)).query_issues(),
        columns=("title",),
    )

    assert cells[row_key("issue", exact.id)] == ("y" * TITLE_LIMIT,)
    (clipped,) = cells[row_key("issue", overlong.id)]
    assert len(clipped) == TITLE_LIMIT
    assert clipped == long_title[: TITLE_LIMIT - 1] + "…"
    # The row still carries the whole title for the Issue view and search.
    assert contexts[row_key("issue", overlong.id)].issue.title == long_title


def test_author_column_is_hidden_by_default_and_marks_a_missing_author() -> None:
    authored = issue("test/repo#1", "Authored")
    anonymous = issue(
        "test/repo#2",
        "Anonymous",
        author=None,
    )

    _contexts, cells = build_rows(
        WorkspaceObservationStore(
            workspace_snapshot(authored, anonymous)
        ).query_issues(),
        columns=("author",),
    )

    assert "author" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", authored.id)] == ("ned2",)
    assert cells[row_key("issue", anonymous.id)] == ("-",)


def test_milestone_and_type_columns_are_hidden_by_default_and_optional() -> None:
    classified = issue("test/repo#1", "Classified")
    plain = issue(
        "test/repo#2",
        "Plain",
        milestone=None,
        issueType=None,
    )

    _contexts, cells = build_rows(
        WorkspaceObservationStore(workspace_snapshot(classified, plain)).query_issues(),
        columns=("milestone", "type"),
    )

    assert "milestone" not in DEFAULT_COLUMNS
    assert "type" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", classified.id)] == ("v1", "Feature")
    assert cells[row_key("issue", plain.id)] == ("-", "-")


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

    contexts, cells = build_rows(
        WorkspaceObservationStore(snapshot).query_issues(), columns=("comments",)
    )

    assert "comments" not in DEFAULT_COLUMNS
    assert cells[row_key("issue", discussed.id)] == ("4",)
    assert cells[row_key("issue", quiet.id)] == ("-",)

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
        WorkspaceObservationStore(workspace_snapshot(selected_issue)).query_issues(),
        columns=("number",),
    )

    number = cells[row_key("issue", selected_issue.id)][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_issue_date_columns_render_iso_dates() -> None:
    selected_issue = issue(
        "test/repo#17",
        "Timestamp test",
        createdAt="2026-08-25T23:30:00Z",
        updatedAt="2026-08-27T01:15:00Z",
    )

    _contexts, cells = build_rows(
        WorkspaceObservationStore(workspace_snapshot(selected_issue)).query_issues(),
        columns=("created", "last_action"),
    )

    assert cells[row_key("issue", selected_issue.id)] == (
        "2026-08-25",
        "2026-08-27",
    )
    assert date_cell(None) == "-"


def test_labels_column_renders_tracker_coloured_chips_and_carries_names() -> None:
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

    _contexts, cells = build_rows(
        WorkspaceObservationStore(snapshot).query_issues(), columns=("labels",)
    )

    chips = cells[row_key("issue", labelled.id)][0]
    assert isinstance(chips, LabelsCell)
    assert chips.plain == " bug   enhancement   zeta "
    assert chips.labels == ("bug", "enhancement", "zeta")
    styles = [str(span.style) for span in chips.spans]
    assert styles == [
        "#ffffff on #d73a4a",
        "#000000 on #a2eeef",
        "#ffffff on #6e7781",
    ]
    empty = cells[row_key("issue", bare.id)][0]
    assert isinstance(empty, LabelsCell)
    assert empty.plain == "-"
    assert empty.labels == ()


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
    result = WorkspaceObservationStore(snapshot).query_issues()

    assert "priority" in DEFAULT_COLUMNS
    assert shown_columns(DEFAULT_COLUMNS, result.rows) == DEFAULT_COLUMNS
    for dark in (True, False):
        _contexts, cells = build_rows(result, columns=("priority", "labels"), dark=dark)

        priority, labels = cells[row_key("issue", urgent.id)]
        assert isinstance(priority, PriorityCell)
        assert priority.plain == " P0 "
        assert priority.priority == "P0"
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

    mixed = WorkspaceObservationStore(
        workspace_snapshot(prioritised, unlabelled)
    ).query_issues()
    assert shown_columns(DEFAULT_COLUMNS, mixed.rows) == DEFAULT_COLUMNS
    _contexts, cells = build_rows(mixed, columns=("priority",))
    # An Issue without a priority label shows nothing and carries no
    # priority: no default is invented.
    absent = cells[row_key("issue", unlabelled.id)][0]
    assert isinstance(absent, PriorityCell)
    assert absent.plain == ""
    assert absent.priority is None
    # The rows keep the order the source gave them.
    assert list(cells) == [
        row_key("issue", prioritised.id),
        row_key("issue", unlabelled.id),
    ]

    plain = WorkspaceObservationStore(workspace_snapshot(unlabelled)).query_issues()
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
        WorkspaceObservationStore(workspace_snapshot(local_issue)).query_issues(),
        columns=("number",),
    )

    number = cells[row_key("issue", "I_local_17")][0]
    assert isinstance(number, IssueNumberCell)
    assert str(number) == "17"
    assert number.justify == "right"


def test_icon_and_title_columns_are_not_sortable() -> None:
    assert not COLUMNS_BY_KEY["issue_state"].sortable
    assert not COLUMNS_BY_KEY["agent_state"].sortable
    assert not COLUMNS_BY_KEY["title"].sortable
    assert COLUMNS_BY_KEY["priority"].sortable


def test_table_view_rejects_empty_or_duplicate_column_layouts() -> None:
    view = IssueTableViewState()

    assert view.with_columns(()).columns == ("agent_state",)
    with pytest.raises(ValueError, match="duplicates"):
        view.with_columns(("title", "title"))


def test_column_catalogue_owns_searchability_and_cells_carry_typed_values() -> None:
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
    # The most active bound Agent Run sets the Glyph; no run shows nothing.
    assert str(agent_state_cell(())) == ""
    assert str(agent_state_cell(("unknown",))) == "○"
    assert str(agent_state_cell(("waiting",))) == "◐"
    assert str(agent_state_cell(("running",))) == "●"
    assert str(agent_state_cell(("running", "running"))) == "●"
    assert str(agent_state_cell(("waiting", "running", "unknown"))) == "●"
    assert str(agent_state_cell(("unknown", "waiting"))) == "◐"
    assert all(IssueNumberCell(number).justify == "right" for number in (2, 10))
    for kind in ("open", "completed", "not-planned", "duplicate"):
        assert IssueStateCell(kind, dark=True).state_kind == kind


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

    contexts, cells = build_rows(WorkspaceObservationStore(snapshot).query_issues())

    selected_key = row_key("issue", selected_issue.id)
    assert len(cells[selected_key]) == len(DEFAULT_COLUMNS) == 7
    number_cell = cells[selected_key][DEFAULT_COLUMNS.index("number")]
    assert str(number_cell) == "1"
    assert isinstance(number_cell, IssueNumberCell)
    assert number_cell.justify == "right"
    assert str(cells[selected_key][DEFAULT_COLUMNS.index("agent_state")]) == "◐"
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

    contexts, cells = build_rows(WorkspaceObservationStore(snapshot).query_issues())

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
        WorkspaceObservationStore(
            workspace_snapshot(open_issue, closed_issue)
        ).query_issues()
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

    contexts, cells = build_rows(
        WorkspaceObservationStore(workspace_snapshot(closed_issue)).query_issues()
    )

    assert contexts == {}
    assert cells == {}


def test_every_column_help_is_its_description_and_the_legend_glyphs() -> None:
    """A header tooltip is the column's own definition, Glyph columns included."""
    for spec in COLUMN_SPECS:
        help_text = column_help(spec)
        assert help_text is not None
        assert help_text.startswith(spec.description), spec.key
    assert {spec.key for spec in COLUMN_SPECS if spec.glyphs} == {
        "issue_state",
        "agent_state",
    }
    assert COLUMNS_BY_KEY["issue_state"].glyphs == LEGEND_ISSUE_STATE
    assert COLUMNS_BY_KEY["agent_state"].glyphs == LEGEND_AGENT_STATE
    agent_help = required(column_help(COLUMNS_BY_KEY["agent_state"]))
    assert ISSUE_STATE_COLUMN_GLYPH.meaning in required(
        column_help(COLUMNS_BY_KEY["issue_state"])
    )
    assert AGENT_STATE_COLUMN_GLYPH.meaning in agent_help
    # The Issue column summarizes bound Agent Runs, which its help says.
    assert "Issue Binding" in agent_help
    assert f"clipped past {TITLE_LIMIT}" in COLUMNS_BY_KEY["title"].description
