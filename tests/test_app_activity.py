from dataclasses import replace
from unittest.mock import Mock

import pytest

from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    footer_keys,
    observation_landed,
    show_query_peer,
    toasts,
    workspace_snapshot,
)
from dashpot.observation.issue_list import row_key
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_records import write_hook_record
from dashpot.sessions.processes import ProcessIdentity
from dashpot.sessions.work_store import ActiveWork, SessionProcess, WorkStore
from dashpot.ui.column_editor import IssueColumnEditor
from dashpot.ui.glyphs import SESSION_STATE_GLYPHS
from dashpot.ui.issue_cells import AgentStateCell
from dashpot.ui.issue_table import IssueTableViewState
from dashpot.ui.keyed_table import capture_selection
from dashpot.ui.marked_widgets import MarkedSelectionList
from dashpot.ui.session_table import SessionTable
from factories import agent_run, hook_record_document, target
from helpers import present, wait_until
from test_app_query_pages import application
from test_app_worktree_launcher import WorktreeCollector
from test_related_rows import query_source, related, related_snapshot

RELATED_ACTIVITY_BACKGROUNDS = {"textual-dark": "#3c1e70", "textual-light": "#e2d9ff"}


def background(style):
    """The hex background a rendered style paints, or nothing unpainted."""
    if style is None or style.bgcolor is None or style.bgcolor.triplet is None:
        return None
    return style.bgcolor.triplet.hex


def activity_cell(table, line):
    """The segments of a rendered row's first cell, its agent-activity cell."""
    width = table.ordered_columns[0].get_render_width(table)
    cell = []
    for segment in line:
        if width <= 0:
            break
        cell.append(segment)
        width -= segment.cell_length
    return cell


@pytest.mark.asyncio
@pytest.mark.parametrize("source_pane", ["sessions", "worktrees", "branches"])
async def test_all_sources_navigation_reentry_and_passive_destinations(source_pane):
    collector = SequenceCollector(related_snapshot())
    app = dashboard_app(collector)
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        tables = {
            "sessions": app.dashboard.sessions_pane().table,
            "worktrees": app.dashboard.worktrees_pane().table,
            "branches": app.dashboard.branches_pane().table,
        }
        source = tables[source_pane]
        queries = {
            "sessions": app.store.query_sessions,
            "worktrees": app.store.query_worktrees,
            "branches": app.store.query_branches,
        }

        def matches():
            key = capture_selection(source)[0]
            row = next(
                (row for row in queries[source_pane]().rows if row.key == key), None
            )
            result = query_source(app.store, row)
            return all(
                table.related_rows == getattr(result, name)
                for name, table in tables.items()
            )

        before = {
            name: (capture_selection(table), table.scroll_offset, tuple(table.rows))
            for name, table in tables.items()
            if name != source_pane
        }
        source.focus()
        await wait_until(matches)
        await pilot.press("down")
        await wait_until(matches)
        assert source.cursor_row == 1
        await pilot.click(source, offset=(2, 1))
        await wait_until(lambda: source.cursor_row == 0 and matches())
        assert before == {
            name: (capture_selection(table), table.scroll_offset, tuple(table.rows))
            for name, table in tables.items()
            if name != source_pane
        }
        await pilot.press("down")
        await pilot.press("2")
        await wait_until(
            lambda: not any(table.related_rows for table in tables.values())
        )
        # Re-entry keeps the cursor and re-emphasizes from where it stayed.
        await pilot.press("1")
        await wait_until(lambda: source.cursor_row == 1 and matches())
        await pilot.press("?")
        await wait_until(
            lambda: not any(table.related_rows for table in tables.values())
        )
        await pilot.press("escape")
        await wait_until(matches)
        assert collector.calls == 1
        assert not app.query_screen.queue_table().related_rows


@pytest.mark.asyncio
async def test_session_destinations_keep_glyph_colors_and_bold_identity_in_both_themes():
    app = dashboard_app(SequenceCollector(related_snapshot()))
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.dashboard.sessions_pane().table
        for theme in ("textual-dark", "textual-light"):
            app.theme = theme
            app.dashboard.set_focus(None)
            await wait_until(lambda table=table: not table.related_rows)
            await pilot.pause()
            baseline = table.render_line(1)
            base_glyph = next(segment for segment in baseline if "●" in segment.text)
            app.dashboard.worktrees_pane().table.focus()
            await wait_until(lambda: bool(table.related_rows))
            line = table.render_line(1)
            glyph = next(segment for segment in line if "●" in segment.text)
            assert glyph.style is not None and base_glyph.style is not None
            assert glyph.style.color == base_glyph.style.color
            assert background(glyph.style) == RELATED_ACTIVITY_BACKGROUNDS[theme]
            for text in ("Codex", "/alpha"):
                segment = next(segment for segment in line if text in segment.text)
                base = next(segment for segment in baseline if text in segment.text)
                assert segment.style is not None and base.style is not None
                assert segment.style.bold and not base.style.bold
                assert segment.style.bgcolor == base.style.bgcolor


@pytest.mark.asyncio
@pytest.mark.parametrize("pane", ["worktrees", "branches"])
async def test_refresh_for_each_new_source_follows_visible_key_and_clears_removed_rows(
    pane,
):
    initial = related_snapshot()
    changed_run = initial.agent_runs[0].model_copy(
        update={"id": "new-run", "observation_target": "/linked", "branch": "feature"}
    )
    changed = initial.model_copy(
        update={
            "agent_runs": (changed_run,),
            "issue_runs": {"I_alpha#2": (changed_run.id,)},
        }
    )
    removed = initial.model_copy(
        update={"projects": (), "agent_runs": (), "issue_runs": {}}
    )
    app = dashboard_app(
        SequenceCollector(initial, changed, RuntimeError("rejected"), removed)
    )
    async with app.run_test(size=(150, 55)):
        await wait_until(lambda: first_load_landed(app))
        tables = {
            "sessions": app.dashboard.sessions_pane().table,
            "worktrees": app.dashboard.worktrees_pane().table,
            "branches": app.dashboard.branches_pane().table,
        }
        queries = {
            "worktrees": app.store.query_worktrees,
            "branches": app.store.query_branches,
        }
        table = tables[pane]
        table.focus()

        def matches():
            key = capture_selection(table)[0]
            source = next((row for row in queries[pane]().rows if row.key == key), None)
            result = query_source(app.store, source)
            return all(
                target.related_rows == getattr(result, name)
                for name, target in tables.items()
            )

        await wait_until(matches)
        key = capture_selection(table)[0]
        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 2) and matches())
        assert capture_selection(table)[0] == key
        accepted = tuple(target.related_rows for target in tables.values())
        app.request_refresh("manual")
        await wait_until(
            lambda: bool(app.observations.errors) and first_load_landed(app)
        )
        assert tuple(target.related_rows for target in tables.values()) == accepted
        app.request_refresh("manual")
        await wait_until(lambda: table.row_count == 0 and matches())
        assert not any(target.related_rows for target in tables.values())


def destination_tables(app):
    return (
        app.dashboard.worktrees_pane().table,
        app.dashboard.branches_pane().table,
    )


def emphasis(app):
    return tuple(table.related_rows for table in destination_tables(app))


def expected(app, run_id):
    rows = related(app.store, run_id, app.query_screen.list_queries.issues)
    return rows.worktrees, rows.branches


@pytest.mark.asyncio
async def test_keyboard_mouse_focus_and_modal_emphasis_leave_other_panes_unchanged():
    collector = SequenceCollector(related_snapshot())
    app = dashboard_app(collector)
    async with app.run_test(size=(120, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        sessions = app.dashboard.sessions_pane().table
        destinations = destination_tables(app)
        before = [
            (capture_selection(table), table.scroll_offset, tuple(table.rows))
            for table in destinations
        ]
        queries = (
            app.query_screen.issue_table.issue_view,
            app.query_screen.list_queries.issues,
            app.query_screen.list_queries.pull_requests,
        )
        sessions.focus()
        await wait_until(lambda: emphasis(app) == expected(app, "one"))
        await pilot.press("down")
        await wait_until(lambda: emphasis(app) == expected(app, "two"))
        await pilot.click(sessions, offset=(2, 1))
        await wait_until(lambda: emphasis(app) == expected(app, "one"))
        assert before == [
            (capture_selection(table), table.scroll_offset, tuple(table.rows))
            for table in destinations
        ]
        assert queries == (
            app.query_screen.issue_table.issue_view,
            app.query_screen.list_queries.issues,
            app.query_screen.list_queries.pull_requests,
        )
        assert collector.calls == 1
        await pilot.press("?")
        await wait_until(lambda: not any(emphasis(app)))
        await pilot.press("escape")
        await wait_until(lambda: emphasis(app) == expected(app, "one"))
        await pilot.press("down")
        await wait_until(lambda: emphasis(app) == expected(app, "two"))
        destinations[0].focus()
        await wait_until(lambda: bool(sessions.related_rows))
        assert not destinations[0].related_rows
        sessions.focus()
        await wait_until(lambda: emphasis(app) == expected(app, "two"))
        assert sessions.cursor_row == 1


@pytest.mark.asyncio
async def test_refresh_switch_reorder_rejection_and_removal_follow_visible_session():
    initial = related_snapshot()
    changed = initial.agent_runs[0].model_copy(
        update={
            "id": "switched-run",
            "state": "unknown",
            "observation_target": "/linked",
            "branch": "feature",
            "issue_id": "I_alpha#2",
        }
    )
    second = initial.model_copy(
        update={
            "agent_runs": (initial.agent_runs[1], changed),
            "issue_runs": {"I_alpha#2": (changed.id,)},
        }
    )
    removed = initial.model_copy(
        update={"agent_runs": (initial.agent_runs[1],), "issue_runs": {}}
    )
    empty = initial.model_copy(update={"agent_runs": (), "issue_runs": {}})
    app = dashboard_app(
        SequenceCollector(initial, second, RuntimeError("rejected"), removed, empty)
    )
    async with app.run_test(size=(120, 55)):
        await wait_until(lambda: first_load_landed(app))
        sessions = app.dashboard.sessions_pane().table
        sessions.focus()
        await wait_until(lambda: emphasis(app) == expected(app, "one"))
        key = capture_selection(sessions)[0]
        app.request_refresh("manual")
        await wait_until(lambda: observation_landed(app, 2))
        assert capture_selection(sessions) == (key, 1)
        await wait_until(lambda: emphasis(app) == expected(app, "switched-run"))
        app.request_refresh("manual")
        await wait_until(
            lambda: bool(app.observations.errors) and first_load_landed(app)
        )
        assert emphasis(app) == expected(app, "switched-run")
        app.request_refresh("manual")
        await wait_until(lambda: sessions.row_count == 1)
        await wait_until(lambda: emphasis(app) == expected(app, "two"))
        assert capture_selection(sessions)[0] != key
        app.request_refresh("manual")
        await wait_until(lambda: sessions.row_count == 0)
        await wait_until(lambda: not any(emphasis(app)))


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(65, 55), (200, 65)])
async def test_activity_alignment_freezing_and_theme_colors(size):
    # Bind the run to the Issue it declares, as the collector's Issue Binding
    # validation does: the page row reads the declaration, the Sessions pane
    # the binding, and the two only agree on an observation shaped like that.
    snapshot = related_snapshot(bindings={"I_alpha#2": ["one"]})
    project = snapshot.projects[0]
    targets = list(project.snapshot.observation_targets)
    targets[0] = targets[0].model_copy(update={"path": "/" + "long-path-" * 35})
    runs = list(snapshot.agent_runs)
    runs[0] = runs[0].model_copy(update={"observation_target": targets[0].path})
    project = project.model_copy(
        update={
            "snapshot": project.snapshot.model_copy(
                update={"observation_targets": tuple(targets)}
            )
        }
    )
    snapshot = snapshot.model_copy(
        update={"projects": (project, snapshot.projects[1]), "agent_runs": runs}
    )
    app = dashboard_app(SequenceCollector(snapshot))
    async with app.run_test(size=size) as pilot:
        await wait_until(lambda: first_load_landed(app))
        tables = (app.dashboard.sessions_pane().table, *destination_tables(app))
        for theme in ("textual-dark", "textual-light"):
            app.theme = theme
            tables[0].focus()
            await pilot.pause()
            positions = []
            for table in tables:
                assert table.ordered_columns[0].width == 1
                assert table.fixed_columns == 1 and table.cell_padding == 1
                header = table.render_line(0).text
                positions.append(table.region.x + header.index("◈"))
                before = table.render_line(0).text.index("◈")
                running_index = next(
                    index
                    for index in range(table.row_count)
                    if str(table.get_row_at(index)[0]) == "●"
                )
                assert table.render_line(running_index + 1).text.index("●") == before
                table.scroll_to(x=100, animate=False, force=True)
                await pilot.pause()
                assert table.render_line(0).text.index("◈") == before
                assert table.render_line(running_index + 1).text.index("●") == before
            assert len(set(positions)) == 1
            await show_query_peer(app, pilot)
            activity = app.query_screen.queue_table().get_cell(
                row_key("issue", "I_alpha#2"), "agent_state"
            )
            assert isinstance(activity, AgentStateCell)
            assert str(activity.style) == SESSION_STATE_GLYPHS["running"].style(
                dark=app.current_theme.dark
            )
            await pilot.press("1")
        # Two zero-weight columns used to let the activity Glyph take spare width.
        app.query_screen.issue_table.issue_view = replace(
            app.query_screen.issue_table.issue_view, columns=("issue_state",)
        )
        app.query_screen.issue_table.reconcile_rows()
        await pilot.pause()
        assert app.query_screen.queue_table().ordered_columns[0].width == 1
        app.query_screen.issue_table.issue_view = replace(
            app.query_screen.issue_table.issue_view, columns=()
        )
        app.query_screen.issue_table.reconcile_rows()
        await pilot.pause()
        assert app.query_screen.queue_table().ordered_columns[0].width == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("theme", sorted(RELATED_ACTIVITY_BACKGROUNDS))
async def test_related_rows_light_the_activity_cell_and_bold_identifying_cells(theme):
    app = dashboard_app(SequenceCollector(related_snapshot()))
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        app.theme = theme
        table = app.dashboard.worktrees_pane().table
        app.dashboard.set_focus(None)
        await wait_until(lambda: not table.related_rows)
        await pilot.pause()
        row_key = next(
            row.key
            for row in app.store.query_worktrees().rows
            if row.project.project_id == "project:alpha" and row.target.path == "/alpha"
        )
        row_index = table.get_row_index(row_key)
        baseline = table.render_line(row_index + 1)
        base_glyph = next(segment for segment in baseline if "●" in segment.text)
        base_path = next(segment for segment in baseline if "/alpha" in segment.text)
        app.dashboard.sessions_pane().table.focus()
        await wait_until(lambda: row_key in table.related_rows)
        await pilot.pause()
        line = table.render_line(row_index + 1)
        glyph = next(segment for segment in line if "●" in segment.text)
        path = next(segment for segment in line if "/alpha" in segment.text)
        assert glyph.style is not None and base_glyph.style is not None
        assert path.style is not None and base_path.style is not None
        assert glyph.style.color == base_glyph.style.color
        assert background(next(iter(line)).style) == RELATED_ACTIVITY_BACKGROUNDS[theme]
        assert background(glyph.style) == RELATED_ACTIVITY_BACKGROUNDS[theme]
        assert background(path.style) == background(base_path.style)
        assert path.style.bold and not base_path.style.bold
        unrelated = next(
            index
            for index, row in enumerate(table.ordered_rows)
            if row.key.value not in table.related_rows
        )
        assert {
            background(segment.style)
            for segment in activity_cell(table, table.render_line(unrelated + 1))
        } == {background(table.rich_style)}
        table.focus()
        await wait_until(lambda: not table.related_rows)


@pytest.mark.asyncio
async def test_a_related_row_without_agent_sessions_still_lights_its_activity_cell():
    app = dashboard_app(SequenceCollector(related_snapshot(runs=[], bindings={})))
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        app.theme = "textual-dark"
        worktrees = app.dashboard.worktrees_pane().table
        branches = app.dashboard.branches_pane().table
        worktrees.focus()
        worktrees.move_cursor(
            row=worktrees.get_row_index(
                next(
                    row.key
                    for row in app.store.query_worktrees().rows
                    if row.project.project_id == "project:alpha"
                    and row.target.path == "/alpha"
                )
            )
        )
        branch_key = next(
            row.key
            for row in app.store.query_branches().rows
            if row.project.project_id == "project:alpha" and row.name == "main"
        )
        await wait_until(lambda: branches.related_rows == frozenset({branch_key}))
        await pilot.pause()
        line = branches.render_line(branches.get_row_index(branch_key) + 1)
        cell = activity_cell(branches, line)
        assert not "".join(segment.text for segment in cell).strip()
        assert {background(segment.style) for segment in cell} == {
            RELATED_ACTIVITY_BACKGROUNDS["textual-dark"]
        }
        name = next(segment for segment in line if "main" in segment.text)
        assert name.style is not None and name.style.bold
        unrelated = next(
            index
            for index, row in enumerate(branches.ordered_rows)
            if row.key.value != branch_key
        )
        other = branches.render_line(unrelated + 1)
        assert not any(
            segment.style is not None and segment.style.bold for segment in other
        )
        assert {
            background(segment.style) for segment in activity_cell(branches, other)
        } == {background(branches.rich_style)}


@pytest.mark.asyncio
@pytest.mark.parametrize("theme", sorted(RELATED_ACTIVITY_BACKGROUNDS))
async def test_pinned_activity_columns_paint_no_background_of_their_own(theme):
    app = dashboard_app(SequenceCollector(related_snapshot()))
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        app.theme = theme
        app.dashboard.set_focus(None)
        await pilot.pause()
        dashboard_tables = app.dashboard.focus_tables()
        await show_query_peer(app, pilot)
        app.query_screen.set_focus(None)
        await pilot.pause()
        pinned = [
            table
            for table in (*dashboard_tables, *app.query_screen.focus_tables())
            if table.fixed_columns
        ]
        # Sessions, Worktrees, Branches, and the Issue table pin their
        # agent-activity column; Pull Requests pins none.
        assert len(pinned) == 4
        for table in pinned:
            assert table.row_count
            assert background(next(iter(table.render_line(1))).style) == (
                background(table.rich_style)
            )


@pytest.mark.asyncio
async def test_column_editor_normalizes_old_choices_and_keeps_activity_fixed():
    view = IssueTableViewState(
        columns=("title", "agent_state", "number", "agent_state")
    )
    assert view.columns == ("agent_state", "title", "number")
    app = dashboard_app(SequenceCollector(related_snapshot()))
    async with app.run_test(size=(120, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        # The shipped app takes no view of its own, so an old choice arrives
        # as apply_issue_columns would deliver it: set on the mounted dashboard.
        app.query_screen.issue_table.issue_view = view
        app.query_screen.queue_table().focus()
        await pilot.pause()
        await pilot.press("c")
        editor = app.screen
        assert isinstance(editor, IssueColumnEditor)
        assert "agent_state" not in editor.column_order
        assert editor.column_order[:2] == ["title", "number"]
        editor.query_one(MarkedSelectionList).deselect_all()
        await pilot.click("#column-apply")
        await wait_until(lambda: app.screen is app.query_screen)
        assert app.query_screen.issue_table.issue_view.columns == ("agent_state",)


@pytest.mark.asyncio
async def test_offscreen_related_worktree_is_styled_only_when_person_scrolls():
    snapshot = related_snapshot()
    project = snapshot.projects[0]
    project = project.model_copy(
        update={
            "snapshot": project.snapshot.model_copy(
                update={
                    "observation_targets": tuple(
                        target(f"/tree-{index:02}") for index in range(20)
                    )
                }
            )
        }
    )
    run = snapshot.agent_runs[0].model_copy(update={"observation_target": "/tree-19"})
    snapshot = snapshot.model_copy(
        update={"projects": (project,), "agent_runs": (run,)}
    )
    app = dashboard_app(SequenceCollector(snapshot))
    async with app.run_test(size=(85, 30)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.dashboard.worktrees_pane().table
        app.dashboard.sessions_pane().table.focus()
        await wait_until(lambda: bool(table.related_rows))
        key = next(iter(table.related_rows))
        assert table.get_row_index(key) == 19
        assert table.scroll_y == 0 and table.cursor_row == 0
        table.scroll_to(y=19, animate=False, force=True)
        await pilot.pause()
        line = table.render_line(20 - int(table.scroll_y))
        path = next(segment for segment in line if "/tree-19" in segment.text)
        assert path.style is not None and path.style.bold
        assert table.cursor_row == 0


@pytest.mark.asyncio
async def test_issue_pages_never_join_dashboard_relationship_emphasis(
    tmp_path,
):
    app = application(tmp_path, collector=WorktreeCollector(tmp_path))
    run = agent_run(
        "run",
        app.queries.sources["issues"].context.project_id,
        issue_id="I_1",
        target_path=str(tmp_path),
    )
    app.observations.scheduler.agent_observer = lambda targets: ([run], [])
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: "I_1" in app.store.resolved and not app.queries.busy)
        request_identities = Mock(wraps=app.request_identities)
        app.request_identities = request_identities
        sessions = app.dashboard.sessions_pane().table
        sessions.focus()
        await wait_until(
            lambda: bool(app.dashboard.worktrees_pane().table.related_rows)
        )
        assert not app.query_screen.queue_table().related_rows
        request_identities.assert_not_called()
        await show_query_peer(app, pilot)
        app.query_screen.queue_table().focus()
        await pilot.press("n")
        await wait_until(
            lambda: app.queries.navigation["issues"].page.issues[0].id == "I_2"
        )
        await pilot.press("1")
        await pilot.pause()
        assert not app.query_screen.queue_table().related_rows
        assert app.dashboard.worktrees_pane().table.related_rows
        assert app.queries.navigation["issues"].page.issues[0].id == "I_2"


@pytest.mark.asyncio
async def test_paged_cursor_survives_observed_hook_session_starting_issue_work(
    tmp_path,
):
    process = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")
    hooks = tmp_path / "hooks"
    write_hook_record(
        hook_record_document(
            str(tmp_path),
            "conversation",
            "codex",
            process,
            state="waiting",
            at="2026-08-27T03:00:00Z",
            event="Stop",
        ),
        hooks,
    )
    app = application(tmp_path, collector=WorktreeCollector(tmp_path))
    app.observations.scheduler.agent_observer = lambda targets: observe_agent_runs(
        targets, hooks, lookup=present(process)
    )
    async with app.run_test(size=(150, 55)):
        sessions = app.dashboard.sessions_pane().table
        await wait_until(lambda: sessions.row_count == 1 and not app.queries.busy)
        sessions.focus()
        before = capture_selection(sessions)[0]
        assert app.store.query_sessions().rows[0].session.session_id == "conversation"
        work = ActiveWork(
            session_key="codex-4242-abcd1234",
            harness="codex",
            session_label="codex pid 4242",
            session_id="conversation",
            session_process=SessionProcess(
                pid=process.pid, started_at=process.started_at
            ),
            issue_id="I_1",
            issue_reference="issue-1",
            binding_provenance="explicit-reference",
            started_at="2026-08-27T03:01:00Z",
            working_directory=str(tmp_path),
            branch="main",
        )
        WorkStore(tmp_path).start(work)
        app.request_refresh("manual")
        await wait_until(
            lambda: app.store.query_sessions().rows[0].session.id == work.run_id
        )
        assert capture_selection(sessions)[0] == before
        assert app.store.query_sessions().rows[0].session.session_id == "conversation"
        await wait_until(
            lambda: bool(app.dashboard.worktrees_pane().table.related_rows)
        )
        assert not app.query_screen.queue_table().related_rows


@pytest.mark.asyncio
async def test_y_copies_the_resume_command_of_an_orphaned_session_only():
    live = agent_run("work:live", harness="claude-code", state="waiting").model_copy(
        update={"session_id": "live-conversation"}
    )
    orphaned = agent_run(
        "work:orphaned",
        harness="claude-code",
        state="unknown",
        target_path="/work tree/292",
        working_directory="/work tree/292/src",
    ).model_copy(update={"session_id": "gone-conversation", "orphaned": True})
    app = dashboard_app(SequenceCollector(workspace_snapshot(runs=[orphaned, live])))
    clipboard = Mock()
    app.copy_to_clipboard = clipboard
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.dashboard.sessions_pane().table
        table.focus()
        await pilot.pause()
        # The live session ranks first; it has nothing to resume, so the key
        # is not offered there.
        assert "y" not in footer_keys(app)
        await pilot.press("y")
        clipboard.assert_not_called()
        await pilot.press("down")
        await wait_until(lambda: "y" in footer_keys(app))
        await pilot.press("y")
        clipboard.assert_called_once_with(
            "cd '/work tree/292' && claude --resume gone-conversation"
        )
        assert toasts(app)[-1].startswith("Resume command sent to clipboard")
        # Moving back withdraws the offer.
        await pilot.press("up")
        await wait_until(lambda: "y" not in footer_keys(app))
        # A row that left the pane after the key press copies nothing.
        app.dashboard.post_message(SessionTable.ResumeCopyRequested("gone-row"))
        await pilot.pause()
        assert clipboard.call_count == 1
