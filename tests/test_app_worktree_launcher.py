from threading import Event
from typing import override
from unittest.mock import Mock

import pytest
from textual.widgets import Static

from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    issue,
    with_first_target,
    workspace_snapshot,
)
from dashpot.core.model import RepositoryStateInventory
from dashpot.repository.worktree_launcher import (
    LauncherConfiguration,
    WorktreeLaunchError,
    configure_worktree_launcher,
)
from dashpot.ui.worktree_table import WorktreeTable
from factories import target
from helpers import wait_until
from test_app_query_pages import LocalOnlyCollector, application


class WorktreeCollector(LocalOnlyCollector):
    def __init__(self, *paths):
        self.paths = paths

    @override
    def observe_targets(self):
        return RepositoryStateInventory(
            targets=tuple(target(str(path)) for path in self.paths), diagnostics=()
        )


@pytest.mark.asyncio
async def test_worktree_enter_and_copy_are_scoped_and_mouse_does_not_launch(tmp_path):
    path = tmp_path / "full 日本語 path"
    path.mkdir()
    snapshot = with_first_target(
        workspace_snapshot(issue("test/repo#1", "First")), path=str(path)
    )
    opener = Mock()
    app = dashboard_app(
        SequenceCollector(snapshot),
        launcher_configuration=LauncherConfiguration(opener),
    )
    clipboard = Mock()
    app.copy_to_clipboard = clipboard
    async with app.run_test(size=(120, 45)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one(WorktreeTable)
        table.focus()
        await pilot.pause()
        await pilot.click(table, offset=(3, 1))
        await pilot.click(table, offset=(3, 1))
        opener.assert_not_called()
        await pilot.press("enter")
        await wait_until(lambda: opener.call_count == 1 and not table.opening)
        opener.assert_called_once_with(path)
        await pilot.press("y")
        clipboard.assert_called_once_with(str(path))
        app.dashboard.branches_pane().table.focus()
        await pilot.press("enter", "y")
        assert app.screen is app.dashboard
        assert opener.call_count == 1 and clipboard.call_count == 1
        search = app.dashboard.issue_filter_bar.search
        search.focus()
        await pilot.press("y")
        assert search.value == "y"
        assert clipboard.call_count == 1


@pytest.mark.asyncio
async def test_pending_request_keeps_captured_path_and_refuses_duplicates(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    snapshot = with_first_target(workspace_snapshot(), path=str(first))
    release = Event()
    captured = []

    def opener(path):
        captured.append(path)
        release.wait(timeout=3)

    app = dashboard_app(
        SequenceCollector(snapshot),
        launcher_configuration=LauncherConfiguration(opener),
    )
    try:
        async with app.run_test(size=(120, 45)) as pilot:
            await wait_until(lambda: first_load_landed(app))
            table = app.query_one(WorktreeTable)
            table.focus()
            await pilot.press("enter")
            await wait_until(lambda: len(captured) == 1)
            await pilot.press("enter", "enter")
            assert captured == [first] and table.opening
            app.dashboard.queue_table().focus()
            release.set()
            await wait_until(lambda: not table.opening)
    finally:
        release.set()


@pytest.mark.asyncio
async def test_bad_settings_leave_observation_and_copy_available(tmp_path):
    settings = tmp_path / "config.toml"
    settings.write_text("worktree_open_command = []")
    config = configure_worktree_launcher(
        path=settings, environment={"TMUX": "socket", "TMUX_PANE": "%8"}
    )
    observed = tmp_path / "unavailable"
    app = application(
        tmp_path,
        collector=WorktreeCollector(observed),
        launcher_configuration=config,
    )
    clipboard = Mock()
    app.copy_to_clipboard = clipboard
    async with app.run_test(size=(120, 45)) as pilot:
        table = app.query_one(WorktreeTable)
        await wait_until(lambda: table.row_count == 1)
        table.focus()
        await pilot.press("enter", "y")
        assert not table.launch_available and not table.opening
        assert not app.screen.active_bindings["enter"].enabled
        assert app.screen.active_bindings["y"].enabled
        clipboard.assert_called_once_with(str(observed))
        assert "worktree_open_command" in str(
            app.query_one("#diagnostics", Static).render()
        )
        assert app.screen is app.dashboard


@pytest.mark.asyncio
async def test_paged_launch_keeps_path_through_refresh_and_empty_footer(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    collector = WorktreeCollector(first)
    release = Event()
    captured = []

    def opener(path):
        captured.append(path)
        release.wait(timeout=5)

    app = application(
        tmp_path,
        collector=collector,
        launcher_configuration=LauncherConfiguration(opener),
    )
    clipboard = Mock()
    app.copy_to_clipboard = clipboard
    try:
        async with app.run_test(size=(120, 45)) as pilot:
            table = app.query_one(WorktreeTable)
            await wait_until(lambda: table.row_count == 1)
            table.focus()
            await pilot.pause()
            bindings = app.screen.active_bindings
            assert bindings["enter"].binding.description == "Open Worktree"
            assert bindings["y"].binding.description == "Copy path"
            assert bindings["enter"].enabled and bindings["y"].enabled
            old_key, _ = app.dashboard.worktrees_pane().highlighted()
            await pilot.press("enter")
            await wait_until(lambda: captured == [first])
            assert not app.screen.active_bindings["enter"].enabled
            collector.paths = (second,)
            app.request_refresh("manual")
            await wait_until(
                lambda: (
                    app.worktree_path(old_key) is None
                    and any(
                        row.target.path == str(second)
                        for row in app.store.query_worktrees().rows
                    )
                )
            )
            await pilot.press("enter", "y")
            assert captured == [first]
            clipboard.assert_called_once_with(str(second))
            release.set()
            await wait_until(lambda: not table.opening)
            app.request_worktree_open(old_key)
            assert captured == [first]
            collector.paths = ()
            app.request_refresh("manual")
            await wait_until(lambda: table.row_count == 0)
            assert not app.screen.active_bindings["enter"].enabled
            assert not app.screen.active_bindings["y"].enabled

            def footer_actions_disabled():
                footer_actions = {
                    widget.key: widget for widget in app.query("FooterKey")
                }
                return all(
                    key in footer_actions and footer_actions[key].has_class("-disabled")
                    for key in ("enter", "y")
                )

            await wait_until(footer_actions_disabled)
            await pilot.press("enter", "y")
            assert captured == [first] and clipboard.call_count == 1
    finally:
        release.set()


@pytest.mark.asyncio
async def test_a_refused_launch_is_a_toast_and_releases_the_row(tmp_path):
    # The launcher's own refusal reaches the person as a toast, and a second
    # Enter is accepted once the refused request has ended.
    path = tmp_path / "refused"
    path.mkdir()
    snapshot = with_first_target(
        workspace_snapshot(issue("test/repo#1", "First")), path=str(path)
    )
    opener = Mock(side_effect=WorktreeLaunchError("launcher exited 2: no tmux"))
    app = dashboard_app(
        SequenceCollector(snapshot),
        launcher_configuration=LauncherConfiguration(opener),
    )
    notify = Mock(wraps=app.notify)
    app.notify = notify
    async with app.run_test(size=(120, 45)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        table = app.query_one(WorktreeTable)
        table.focus()
        await pilot.press("enter")
        await wait_until(lambda: opener.call_count == 1 and not table.opening)
        await pilot.press("enter")
        await wait_until(lambda: opener.call_count == 2 and not table.opening)
    errors = [
        call.args[0]
        for call in notify.call_args_list
        if call.kwargs.get("severity") == "error"
    ]
    assert errors == ["launcher exited 2: no tmux"] * 2
