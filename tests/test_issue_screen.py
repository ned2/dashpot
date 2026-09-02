"""The full-screen Issue view, its metadata, the column editor and Legend."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from rich.text import Text
from textual.content import Content
from textual.dom import DOMNode
from textual.style import Style
from textual.widget import Widget
from textual.widgets import DataTable, Input, Markdown, Static

from app_harness import (
    NOW,
    SequenceCollector,
    footer_keys,
    issue,
    issue_metadata_text,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot import session_list
from dashpot.app import DashpotApp
from dashpot.column_editor import IssueColumnEditor
from dashpot.detail_fields import DetailFields, detail_items_text
from dashpot.issue_cells import IssueStateCell
from dashpot.issue_list import IssueListQuery, query_issue_list, row_key
from dashpot.issue_profile import IssueProfile
from dashpot.issue_table import IssueTableViewState
from dashpot.issue_view import (
    IssueScreen,
    issue_byline,
    issue_location,
    issue_metadata_items,
    issue_state_class,
)
from dashpot.legend import LEGEND, LegendScreen, legend_glyphs, section_heading
from dashpot.model import AgentRun, IssueActivity, LinkedPullRequest
from dashpot.observation_store import WorkspaceObservationStore
from helpers import wait_until


@pytest.mark.parametrize(
    ("state", "reason", "state_class", "dark_color", "light_color"),
    [
        ("open", None, "-issue-open", "#238636", "#1f883d"),
        ("closed", "completed", "-issue-completed", "#8957e5", "#8250df"),
        (
            "closed",
            "not-planned",
            "-issue-not-planned",
            "#656c76",
            "#59636e",
        ),
        ("closed", "duplicate", "-issue-duplicate", "#656c76", "#59636e"),
    ],
)
@pytest.mark.asyncio
async def test_issue_view_tracks_github_issue_state_colors(
    state: str,
    reason: str | None,
    state_class: str,
    dark_color: str,
    light_color: str,
) -> None:
    selected_issue = issue(
        "test/repo#1",
        "Stateful",
        state=state,
        stateReason=reason,
        closedAt=NOW if state == "closed" else None,
    )
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(selected_issue)),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"open", "closed"}))
        ),
    )

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        table = app.query_one("#queue", DataTable)
        issue_key = row_key("issue", selected_issue.id)
        state_cell = table.get_cell(issue_key, "issue_state")
        assert isinstance(state_cell, IssueStateCell)
        assert state_cell.plain == "■"
        assert str(state_cell.style).casefold() == dark_color

        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        body = view.query_one("#issue-view-body")
        metadata = view.query_one("#issue-view-metadata")

        assert issue_state_class(selected_issue) == state_class
        assert view.query_one("#issue-view").has_class(state_class)
        # Both border lines carry the state colour: in full on the focused
        # pane and dimmed on the other, so focus still reads without a bar.
        assert body.has_focus
        assert border_color(body) == dark_color
        assert body.styles.border_top[1].a == 1
        assert border_color(metadata) == dark_color
        assert 0 < metadata.styles.border_top[1].a < 1
        # The titles keep the ordinary text colour, and the State value is a
        # chip on the state colour.
        for pane in (body, metadata):
            assert pane.styles.border_title_color.a == 1
            assert pane.styles.border_title_color.hex.casefold() != dark_color
        assert state_chip_background(view) == dark_color
        assert state_chip_text(view).startswith(state)

        await pilot.press("tab")
        assert metadata.has_focus
        assert border_color(metadata) == dark_color
        assert metadata.styles.border_top[1].a == 1
        assert 0 < body.styles.border_top[1].a < 1

        app.theme = "textual-light"
        await wait_until(lambda: border_color(metadata) == light_color)

        assert border_color(body) == light_color
        assert state_chip_background(view) == light_color
        light_state_cell = table.get_cell(issue_key, "issue_state")
        assert isinstance(light_state_cell, IssueStateCell)
        assert light_state_cell.plain == "■"
        assert str(light_state_cell.style).casefold() == light_color


def border_color(pane: Widget) -> str:
    """The pane's border colour without its alpha."""
    return pane.styles.border_top[1].hex.casefold()[:7]


def state_chip(view: DOMNode) -> Text:
    row = next(
        row
        for row in view.query_one("#issue-view-metadata", DetailFields).rows
        if row.item.label == "State"
    )
    assert isinstance(row.item.value, Text)
    return row.item.value


def state_chip_text(view: DOMNode) -> str:
    return state_chip(view).plain.strip()


def state_chip_background(view: DOMNode) -> str:
    return str(state_chip(view).style).casefold().split(" on ")[1]


@pytest.mark.asyncio
async def test_issue_view_color_follows_the_opened_issue() -> None:
    open_issue = issue("test/repo#1", "Open")
    completed_issue = issue(
        "test/repo#2",
        "Completed",
        state="closed",
        stateReason="completed",
        closedAt=NOW,
    )
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(open_issue, completed_issue)),
        refresh_seconds=0,
        issue_view=IssueTableViewState(
            query=IssueListQuery(states=frozenset({"open", "closed"}))
        ),
    )

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.store.revision == 1)

        app.dashboard.open_issue(row_key("issue", open_issue.id))
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.pause()
        view = app.screen.query_one("#issue-view")
        assert view.has_class("-issue-open")
        assert border_color(app.screen.query_one("#issue-view-body")) == "#238636"

        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, IssueScreen))
        app.dashboard.open_issue(row_key("issue", completed_issue.id))
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.pause()
        view = app.screen.query_one("#issue-view")
        assert view.has_class("-issue-completed")
        assert not view.has_class("-issue-open")
        assert border_color(app.screen.query_one("#issue-view-body")) == "#8957e5"


@pytest.mark.asyncio
async def test_column_editor_applies_visibility_and_order_without_losing_selection() -> (
    None
):
    snapshot = workspace_snapshot(
        issue("test/repo#1", "First"),
        issue("test/repo#2", "Second"),
    )
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )

    async with app.run_test(size=(100, 30)) as pilot:
        table = app.query_one("#queue", DataTable)
        selected_key = row_key("issue", "I_test/repo#2")
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.dashboard.selected_row_key == selected_key)

        await pilot.press("c")
        editor = app.screen
        assert isinstance(editor, IssueColumnEditor)
        selections = editor.query_one("#column-editor-list")
        selected_line = selections.render_line(editor.column_order.index("title"))
        unselected_line = selections.render_line(editor.column_order.index("project"))
        assert selected_line.text.startswith("▐X▌")
        assert unselected_line.text.startswith("▐ ▌")
        assert (
            list(selected_line)[1].style.color == list(unselected_line)[1].style.color
        )
        selections.select("project")
        selections.highlighted = editor.column_order.index("last_action")
        assert await pilot.click("#column-up")
        await pilot.pause()
        assert await pilot.click("#column-apply")
        await pilot.pause()

        assert app.dashboard.issue_view.columns == (
            "issue_state",
            "agent_state",
            "number",
            "title",
            "priority",
            "last_action",
            "labels",
            "project",
        )
        assert [key.value for key in table.columns] == list(
            app.dashboard.issue_view.columns
        )
        assert app.dashboard.selected_row_key == selected_key
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        assert selected == selected_key


def test_issue_byline_frames_the_issue_as_opened_by_its_author() -> None:
    now = datetime(2026, 8, 29, 5, 33, 4, tzinfo=UTC)
    selected_issue = issue(
        "test/repo#12",
        "Byline",
        createdAt="2026-08-26T05:33:04Z",
    )

    assert issue_byline(selected_issue, now=now) == "opened 3d ago by ned2"

    anonymous_issue = issue(
        "test/repo#12",
        "Byline",
        author=None,
        createdAt="2026-08-29T05:20:00Z",
    )

    assert issue_byline(anonymous_issue, now=now) == "opened 13m ago"


def test_issue_location_is_the_url_or_the_local_file_line() -> None:
    hosted = issue("test/repo#12", "Hosted")
    assert hosted.location.kind == "github"
    assert issue_location(hosted) == hosted.location.url

    local = issue(
        "test/repo#13",
        "Local",
        location={"kind": "markdown", "path": "TASKS.md", "line": 7},
    )
    assert issue_location(local) == "TASKS.md:7"


def test_issue_metadata_excludes_labels_used_as_priority() -> None:
    selected_issue = issue(
        "test/repo#1",
        "First",
        labels=[
            "bug",
            "priority/p0",
            "priority/p1",
            "priority/p2",
            "priority/p3",
            "critical",
            "high",
            "medium",
            "low",
        ],
    )
    context = query_issue_list(workspace_snapshot(selected_issue)).rows[0]

    detail = issue_metadata_text(context)

    assert "Priority: P0" in detail
    assert "Labels: bug" in detail
    assert "priority/" not in detail
    assert "critical" not in detail
    assert "high" not in detail
    assert "medium" not in detail
    assert "low" not in detail
    # Without a recognized label the priority is absent, never a default.
    unprioritised = issue(
        "test/repo#2",
        "Second",
        labels=["bug"],
    )
    context = query_issue_list(workspace_snapshot(unprioritised)).rows[0]

    assert "Priority: -" in issue_metadata_text(context)


def detail_plain(root: DOMNode, selector: str) -> str:
    return root.query_one(selector, DetailFields).plain


@pytest.mark.asyncio
async def test_issue_view_uses_one_current_store_projection() -> None:
    selected_issue = issue("test/repo#1", "First")
    snapshot = workspace_snapshot(selected_issue)
    store = WorkspaceObservationStore(snapshot)
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=store,
    )
    observed_run = AgentRun(
        id="codex-session:current",
        harness="codex",
        process_or_session="current",
        state="running",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="issue/current",
        issue_id=selected_issue.id,
        issue_reference_hint=selected_issue.reference,
    )

    async with app.run_test(size=(80, 24)) as pilot:
        selected_key = row_key("issue", selected_issue.id)
        await wait_until(lambda: app.dashboard.selected_row_key == selected_key)
        await pilot.pause()
        stale_row = app.dashboard.rows_by_key[selected_key]
        assert stale_row.project_runs == ()

        store.replace_agent_runs([observed_run], {selected_issue.id: [observed_run.id]})
        app.dashboard.open_issue(selected_key)
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        await pilot.pause()

        assert "codex-session:current (running, issue/current)" in detail_plain(
            app.screen, "#issue-view-metadata"
        )


def _issue_view_app(
    *issues: IssueProfile, runs: list[AgentRun] | None = None
) -> DashpotApp:
    snapshot = workspace_snapshot(*issues, runs=runs)
    return DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(snapshot),
    )


@pytest.mark.asyncio
async def test_enter_opens_the_issue_view_and_escape_restores_the_table() -> None:
    first = issue("test/repo#1", "First")
    second = issue(
        "test/repo#2",
        "Second",
        body=(
            "# Heading\n\nSome *emphasis* and a [link](https://example.test).\n\n"
            "- one\n- two\n"
        ),
    )
    app = _issue_view_app(first, second)

    async with app.run_test(size=(120, 36)) as pilot:
        table = app.query_one("#queue", DataTable)
        search = app.query_one("#issue-search", Input)
        selected_key = row_key("issue", second.id)
        table.move_cursor(row=table.get_row_index(selected_key), animate=False)
        await wait_until(lambda: app.dashboard.selected_row_key == selected_key)
        search.value = "s"
        await pilot.pause()
        table.focus()

        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        assert isinstance(view, IssueScreen)
        assert not view.query("#issue-view-title")
        # One heading line: where the Issue lives pushed left, and when it
        # was opened pushed right.
        location_widget = view.query_one("#issue-view-location", Static)
        subtitle_widget = view.query_one("#issue-view-subtitle", Static)
        assert second.location.kind == "github"
        assert str(location_widget.render()) == second.location.url
        subtitle = str(subtitle_widget.render())
        assert subtitle.startswith("opened ")
        assert subtitle.endswith(" by ned2")
        assert " · " not in subtitle
        assert subtitle_widget.styles.text_align == "right"
        assert subtitle_widget.styles.text_style.italic
        heading = view.query_one("#issue-view-heading")
        assert heading.region.height == 1
        assert location_widget.region.y == subtitle_widget.region.y
        assert location_widget.region.x == heading.region.x
        assert location_widget.region.right <= subtitle_widget.region.x
        assert subtitle_widget.region.right == heading.region.right
        markdown = view.query_one("#issue-view-markdown", Markdown)
        assert markdown.region.y == heading.region.bottom
        assert markdown.query("MarkdownH1")
        assert markdown.query("MarkdownBulletList")
        assert not view.query("#issue-view-empty")
        assert view.query_one("#issue-view-body").has_focus
        assert not view.stacked
        # Both panes share the main screen's thin inline-title border, and
        # focus is still cued by the border colour rather than a heavier bar.
        body = view.query_one("#issue-view-body")
        metadata = view.query_one("#issue-view-metadata")
        assert body._border_title is not None
        assert body._border_title.plain == "#2: Second"
        assert (
            body.styles.border_title_color
            == metadata.styles.border_title_color
            == app.dashboard.query_one("#queue-pane").styles.border_title_color
        )
        assert body.styles.border_top[0] == metadata.styles.border_top[0] == "round"
        assert body.styles.border_top[1] != metadata.styles.border_top[1]

        await pilot.press("tab")
        assert view.query_one("#issue-view-metadata").has_focus
        assert metadata.styles.border_top[1] != body.styles.border_top[1]
        await pilot.press("shift+tab")
        assert view.query_one("#issue-view-body").has_focus

        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, IssueScreen))
        assert app.dashboard.selected_row_key == selected_key
        assert app.query_one("#issue-search", Input).value == "s"
        assert app.dashboard.issue_view.query.text == "s"
        assert table.cursor_row == table.get_row_index(selected_key)
        assert table.has_focus


@pytest.mark.asyncio
async def test_issue_view_shows_an_intentional_empty_state_for_a_blank_body() -> None:
    blank = issue(
        "test/repo#1",
        "Blank",
        body="   \n",
    )
    app = _issue_view_app(blank)

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(
            lambda: app.dashboard.selected_row_key == row_key("issue", blank.id)
        )
        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        view = app.screen
        assert not view.query("#issue-view-markdown")
        assert (
            str(view.query_one("#issue-view-empty", Static).render())
            == "This Issue has no description."
        )


@pytest.mark.asyncio
async def test_issue_view_does_nothing_without_an_issue_row() -> None:
    app = _issue_view_app()

    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert app.dashboard.selected_row_key is None
        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await pilot.pause()
        await app.run_action("screen.open_issue")
        await pilot.pause()
        assert not isinstance(app.screen, IssueScreen)


@pytest.mark.asyncio
async def test_issue_view_stacks_metadata_under_the_body_in_compact_terminals() -> None:
    app = _issue_view_app(issue("test/repo#1", "Compact"))

    async with app.run_test(size=(70, 30)) as pilot:
        await wait_until(lambda: app.dashboard.selected_row_key is not None)
        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
        view = app.screen
        assert isinstance(view, IssueScreen)
        await wait_until(lambda: view.stacked)
        body = view.query_one("#issue-view-body")
        metadata = view.query_one("#issue-view-metadata")
        await wait_until(
            lambda: metadata.region.y >= body.region.y + body.region.height
        )
        assert metadata.region.width == body.region.width


@pytest.mark.asyncio
async def test_refresh_while_the_issue_view_is_open_still_reaches_the_dashboard() -> (
    None
):
    before = workspace_snapshot(issue("test/repo#1", "Before"))
    after = workspace_snapshot(
        issue("test/repo#1", "Before"), issue("test/repo#2", "Arrived")
    )
    app = DashpotApp(
        SequenceCollector(after),
        refresh_seconds=0,
        observation_store=WorkspaceObservationStore(before),
    )

    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: app.dashboard.selected_row_key is not None)
        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        await app.run_action("refresh")
        await wait_until(
            lambda: app.dashboard.query_one("#queue", DataTable).row_count == 2
        )
        assert isinstance(app.screen, IssueScreen)

        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, IssueScreen))
        assert app.query_one("#queue", DataTable).row_count == 2


def test_issue_metadata_covers_the_profile_and_marks_absent_values() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    parent = issue("test/repo#1", "Parent")
    child = issue(
        "test/repo#2",
        "Child",
        relationships={
            "parent": parent.id,
            "subIssues": [],
            "blockedBy": ["I_elsewhere"],
            "blocking": [],
        },
        labels=["priority/p1", "bug"],
        assignees=["ned2"],
        createdAt="2026-08-26T12:00:00Z",
        updatedAt="2026-08-29T11:30:00Z",
    )
    run = AgentRun(
        id="run-1",
        harness="codex",
        process_or_session="1",
        state="running",
        observation_target="/repo",
        observation_project_id="project:test-repo",
        branch="feature/child",
        issue_id=None,
        issue_reference_hint=None,
    )
    snapshot = workspace_snapshot(parent, child, runs=[run])
    snapshot = snapshot.model_copy(
        update={"issue_runs": {**snapshot.issue_runs, child.id: (run.id,)}}
    )
    snapshot = with_first_project_snapshot(
        snapshot,
        issue_activity={
            child.id: IssueActivity(
                comment_count=2,
                linked_pull_requests=[
                    LinkedPullRequest(
                        number=9,
                        url="https://github.com/test/repo/pull/9",
                        state="merged",
                    )
                ],
            )
        },
    )
    context = next(row for row in query_issue_list(snapshot).rows if row.issue is child)

    text = detail_items_text(issue_metadata_items(context, now=now))

    assert text == "\n".join(
        [
            "State: open",
            "Author: ned2",
            "Assignees: ned2",
            "Labels: bug",
            "Priority: P1",
            "Type: Feature",
            "Milestone: v1",
            "Created: 2026-08-26 (3d ago)",
            "Updated: 2026-08-29 (30m ago)",
            "Closed: -",
            "Comments: 2",
            "Pull requests:",
            "  #9 merged https://github.com/test/repo/pull/9",
            "Relationships:",
            "  Parent: #1 Parent",
            "  Blocked by: I_elsewhere",
            "Agent sessions:",
            "  run-1 (running, feature/child)",
        ]
    )

    bare = issue(
        "test/repo#3",
        "Bare",
        author=None,
        issueType=None,
        milestone=None,
        labels=[],
        relationships={
            "parent": None,
            "subIssues": [],
            "blockedBy": [],
            "blocking": [],
        },
        state="closed",
        stateReason="not-planned",
        closedAt="2026-08-29T11:00:00Z",
    )
    bare_context = query_issue_list(
        workspace_snapshot(bare), IssueListQuery(states=frozenset({"closed"}))
    ).rows[0]

    bare_text = detail_items_text(issue_metadata_items(bare_context, now=now))

    assert "State: closed as not-planned" in bare_text
    assert "Author: -" in bare_text
    assert "Assignees: unassigned" in bare_text
    assert "Labels: -" in bare_text
    assert "Type: -\nMilestone: -" in bare_text
    assert "Closed: 2026-08-29 (1h ago)" in bare_text
    assert (
        "Comments: 0\nPull requests:\n  -\nRelationships:\n  -\nAgent sessions:\n  -"
    ) in bare_text


def test_issue_view_renders_labels_as_tracker_coloured_chips() -> None:
    labelled = issue(
        "test/repo#1",
        "Labelled",
        labels=["bug", "priority/p1"],
    )
    snapshot = with_first_project_snapshot(
        workspace_snapshot(labelled), label_colors={"bug": "d73a4a"}
    )
    context = query_issue_list(snapshot).rows[0]

    items = issue_metadata_items(context)
    labels = next(item for item in items if item.label == "Labels")
    assert isinstance(labels.value, Text)
    assert labels.value.plain == " bug "
    assert [str(span.style) for span in labels.value.spans] == ["#ffffff on #d73a4a"]
    assert "Labels: bug" in detail_items_text(items)


@pytest.mark.asyncio
async def test_question_mark_opens_the_legend_and_escape_closes_it() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert "question_mark" in footer_keys(app)

        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        screen = app.screen
        headings = [
            str(heading.render()) for heading in screen.query(".legend-heading")
        ]
        assert headings[0] == "SESSIONS · STATE"
        assert headings[-1] == "KEYS"
        assert headings[:-1] == [section_heading(section) for section in LEGEND]
        rendered = "\n".join(
            str(section.render()) for section in screen.query(".legend-section")
        )
        for glyph in legend_glyphs():
            assert glyph.symbol in rendered
            assert glyph.meaning in rendered
        keys = rendered.splitlines()
        assert any(line.startswith("?") and line.endswith("Legend") for line in keys)
        assert any(line.startswith("q") and line.endswith("Quit") for line in keys)
        # A dashboard key proves the screen's bindings reach the Legend too.
        assert any(
            line.startswith("s") and line.endswith("Sort column") for line in keys
        )
        # A colour-bearing Glyph shows the swatch the cell would.
        running = session_list.STATE_GLYPHS["running"]
        sessions = screen.query_one("#legend-section-0", Static)
        content = sessions.render()
        assert isinstance(content, Content)
        span_style = content.spans[0].style
        assert isinstance(span_style, Style)
        swatch = span_style.foreground
        assert swatch is not None
        assert swatch.hex6.casefold() == running.style(dark=app.current_theme.dark)

        # A second ? is absorbed by the Legend rather than stacking another.
        await pilot.press("question_mark")
        await wait_until(lambda: not isinstance(app.screen, LegendScreen))
        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        await pilot.press("escape")
        await wait_until(lambda: not isinstance(app.screen, LegendScreen))
        assert app.query_one("#sessions", DataTable).has_focus


@pytest.mark.asyncio
async def test_dashboard_keys_are_not_on_the_issue_views_binding_chain() -> None:
    app = DashpotApp(
        SequenceCollector(
            workspace_snapshot(
                issue("test/repo#1", "First"), issue("test/repo#2", "Second")
            )
        ),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        sort = app.dashboard.issue_view.sort
        states = app.dashboard.issue_view.query.states
        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        for key in ("c", "slash", "o", "s", "shift+s", "enter"):
            await pilot.press(key)
            await pilot.pause()

        # The dashboard keys live on the DashboardScreen, which is below the
        # Issue view in the screen stack, so they are never dispatched here:
        # no editor stacked over the Issue view, the dashboard's search not
        # focused, its sort and state filter unchanged.
        assert isinstance(app.screen, IssueScreen)
        assert not app.dashboard.query_one("#issue-search", Input).has_focus
        assert app.dashboard.issue_view.sort == sort
        assert app.dashboard.issue_view.query.states == states
        assert len(app.screen_stack) == 2


@pytest.mark.asyncio
async def test_legend_is_reachable_from_the_issue_view() -> None:
    app = DashpotApp(
        SequenceCollector(workspace_snapshot(issue("test/repo#1", "First"))),
        refresh_seconds=0,
    )

    async with app.run_test(size=(100, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        app.dashboard.queue_table().focus()
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))

        await pilot.press("question_mark")
        await wait_until(lambda: isinstance(app.screen, LegendScreen))
        await pilot.press("escape")
        await wait_until(lambda: isinstance(app.screen, IssueScreen))
