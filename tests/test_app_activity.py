from dataclasses import replace
from unittest.mock import Mock

import pytest

from app_harness import SequenceCollector
from dashpot.agents import observe_agent_runs
from dashpot.app import DashpotApp
from dashpot.column_editor import IssueColumnEditor
from dashpot.glyphs import SESSION_STATE_GLYPHS
from dashpot.hook_records import write_hook_record
from dashpot.issue_cells import AgentStateCell
from dashpot.issue_list import row_key
from dashpot.issue_table import IssueTableViewState
from dashpot.keyed_table import capture_selection
from dashpot.marked_widgets import MarkedSelectionList
from dashpot.processes import ProcessIdentity
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
from factories import agent_run, hook_record_document, target
from helpers import present, wait_until
from test_app_worktree_launcher import WorktreeCollector
from test_paged_app import application
from test_related_rows import related, related_snapshot


def destination_tables(app):
    return (
        app.dashboard.worktrees_pane().table,
        app.dashboard.branches_pane().table,
        app.dashboard.queue_table(),
    )


def emphasis(app):
    return tuple(table.related_rows for table in destination_tables(app))


def expected(app, run_id):
    rows = related(app.store, run_id, app.dashboard.issue_view.query)
    return rows.worktrees, rows.branches, rows.issues


@pytest.mark.asyncio
async def test_keyboard_mouse_focus_and_modal_emphasis_leave_other_panes_unchanged():
    collector = SequenceCollector(related_snapshot())
    app = DashpotApp(collector, refresh_seconds=0)
    async with app.run_test(size=(120, 55)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        sessions = app.dashboard.sessions_pane().table
        destinations = destination_tables(app)
        before = [
            (capture_selection(table), table.scroll_offset, tuple(table.rows))
            for table in destinations
        ]
        queries = (app.dashboard.issue_view, app.dashboard.pull_request_query)
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
        assert queries == (app.dashboard.issue_view, app.dashboard.pull_request_query)
        assert collector.calls == 1
        await pilot.press("?")
        await wait_until(lambda: not any(emphasis(app)))
        await pilot.press("escape")
        await wait_until(lambda: emphasis(app) == expected(app, "one"))
        destinations[0].focus()
        await wait_until(lambda: not any(emphasis(app)))
        sessions.focus()
        await wait_until(lambda: emphasis(app) == expected(app, "one"))


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
    app = DashpotApp(
        SequenceCollector(initial, second, RuntimeError("rejected"), removed, empty),
        refresh_seconds=0,
    )
    async with app.run_test(size=(120, 55)):
        await wait_until(lambda: app.store.revision == 1)
        sessions = app.dashboard.sessions_pane().table
        sessions.focus()
        await wait_until(lambda: emphasis(app) == expected(app, "one"))
        key = capture_selection(sessions)[0]
        app.request_refresh("manual")
        await wait_until(lambda: app.store.revision == 2)
        assert capture_selection(sessions) == (key, 1)
        await wait_until(lambda: emphasis(app) == expected(app, "switched-run"))
        app.request_refresh("manual")
        await wait_until(lambda: bool(app.observation_errors))
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
    snapshot = related_snapshot()
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
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)
    async with app.run_test(size=size) as pilot:
        await wait_until(lambda: app.store.revision == 1)
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
            activity = app.dashboard.queue_table().get_cell(
                row_key("issue", "I_alpha#1"), "agent_state"
            )
            assert isinstance(activity, AgentStateCell)
            assert str(activity.style) == SESSION_STATE_GLYPHS["running"].style(
                dark=app.current_theme.dark
            )
        # Two zero-weight columns used to let the activity Glyph take spare width.
        app.dashboard.issue_view = replace(
            app.dashboard.issue_view, columns=("issue_state",)
        )
        app.dashboard.reconcile_rows()
        await pilot.pause()
        assert app.dashboard.queue_table().ordered_columns[0].width == 1
        app.dashboard.issue_view = replace(app.dashboard.issue_view, columns=())
        app.dashboard.reconcile_rows()
        await pilot.pause()
        assert app.dashboard.queue_table().ordered_columns[0].width == 1


@pytest.mark.asyncio
async def test_related_rows_have_background_and_bold_without_losing_glyph_colors():
    app = DashpotApp(SequenceCollector(related_snapshot()), refresh_seconds=0)
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        for theme in ("textual-dark", "textual-light"):
            app.theme = theme
            app.dashboard.branches_pane().table.focus()
            await pilot.pause()
            table = app.dashboard.worktrees_pane().table
            row_key = next(
                row.key
                for row in app.store.query_worktrees().rows
                if row.project.project_id == "project:alpha"
                and row.target.path == "/alpha"
            )
            row_index = table.get_row_index(row_key)
            baseline = table.render_line(row_index + 1)
            base_glyph = next(segment for segment in baseline if "●" in segment.text)
            app.dashboard.sessions_pane().table.focus()
            await wait_until(
                lambda row_key=row_key, table=table: row_key in table.related_rows
            )
            line = table.render_line(row_index + 1)
            glyph = next(segment for segment in line if "●" in segment.text)
            path = next(segment for segment in line if "/alpha" in segment.text)
            assert (
                path.style is not None
                and glyph.style is not None
                and base_glyph.style is not None
            )
            assert path.style.bold
            assert glyph.style.color == base_glyph.style.color
            assert glyph.style.bgcolor != base_glyph.style.bgcolor
            assert glyph.style.bgcolor == path.style.bgcolor
            table.focus()
            await wait_until(lambda table=table: not table.related_rows)


@pytest.mark.asyncio
async def test_column_editor_normalizes_old_choices_and_keeps_activity_fixed():
    view = IssueTableViewState(
        columns=("title", "agent_state", "number", "agent_state")
    )
    assert view.columns == ("agent_state", "title", "number")
    app = DashpotApp(
        SequenceCollector(related_snapshot()), refresh_seconds=0, issue_view=view
    )
    async with app.run_test(size=(120, 55)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("c")
        editor = app.screen
        assert isinstance(editor, IssueColumnEditor)
        assert "agent_state" not in editor.column_order
        editor.query_one(MarkedSelectionList).deselect_all()
        await pilot.click("#column-apply")
        await wait_until(lambda: app.screen is app.dashboard)
        assert app.dashboard.issue_view.columns == ("agent_state",)


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
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0)
    async with app.run_test(size=(85, 30)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
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
async def test_paged_issue_emphasis_uses_only_current_page_without_resolving_on_focus(
    tmp_path,
):
    app = application(tmp_path, collector=WorktreeCollector(tmp_path))
    run = agent_run(
        "run",
        app.sources["issues"].context.project_id,
        issue_id="I_1",
        target_path=str(tmp_path),
    )
    app.scheduler.agent_observer = lambda targets: ([run], [])
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(
            lambda: "I_1" in app.paged_store.resolved and not app.query_busy
        )
        request_identities = Mock(wraps=app.request_identities)
        app.request_identities = request_identities
        sessions = app.dashboard.sessions_pane().table
        sessions.focus()
        await wait_until(lambda: bool(app.dashboard.queue_table().related_rows))
        request_identities.assert_not_called()
        app.dashboard.queue_table().focus()
        await pilot.press("n")
        await wait_until(lambda: app.navigation["issues"].page.issues[0].id == "I_2")
        sessions.focus()
        await pilot.pause()
        assert not app.dashboard.queue_table().related_rows
        assert app.dashboard.worktrees_pane().table.related_rows
        assert app.navigation["issues"].page.issues[0].id == "I_2"


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
    app.scheduler.agent_observer = lambda targets: observe_agent_runs(
        targets, hooks, lookup=present(process)
    )
    async with app.run_test(size=(150, 55)):
        sessions = app.dashboard.sessions_pane().table
        await wait_until(lambda: sessions.row_count == 1 and not app.query_busy)
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
        await wait_until(lambda: bool(app.dashboard.queue_table().related_rows))
