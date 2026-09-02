"""The ``f`` key: the one explicit mutation on the dashboard, fetch and prune.

Observation stays passive; a fetch runs only on the key, only at the
Repository Anchor whose refs supplied the Branch observation, and its result
is observed the passive way afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from textual.widgets import Footer, Static
from textual.widgets._footer import FooterKey

from app_harness import (
    SequenceCollector,
    footer_keys,
    issue,
    pane_subtitle,
    with_first_project,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.app import DashpotApp
from dashpot.fetch import FetchReport, RemoteFetch, fetch_remotes
from dashpot.git import Git
from dashpot.legend import LegendScreen
from dashpot.model import Branch, WorkspaceSnapshot
from factories import SequenceRunner, completed
from helpers import wait_until

ANCHOR = "/repo"
STALE_FETCH = (datetime.now(UTC) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
FRESH_FETCH = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def local(name: str) -> Branch:
    return Branch(
        refname=f"refs/heads/{name}",
        name=name,
        remote=None,
        head="aaa",
        committed_at="2026-08-25T00:00:00Z",
        upstream=f"origin/{name}",
    )


def remote(name: str, remote_name: str = "origin") -> Branch:
    return Branch(
        refname=f"refs/remotes/{remote_name}/{name}",
        name=name,
        remote=remote_name,
        head="aaa",
        committed_at="2026-08-25T00:00:00Z",
    )


def observed(
    *branches: Branch,
    fetched_at: str | None = STALE_FETCH,
    branch_anchor: str | None = ANCHOR,
    anchors: tuple[str, ...] = (ANCHOR,),
) -> WorkspaceSnapshot:
    snapshot = with_first_project_snapshot(
        workspace_snapshot(issue("test/repo#1", "First")),
        branches=list(branches),
        fetched_at=fetched_at,
        integration_ref="refs/remotes/origin/main",
        branch_anchor=branch_anchor,
    )
    return with_first_project(snapshot, anchors=anchors, primary_anchor=anchors[0])


BEFORE = observed(local("main"), remote("main"), remote("feature"))
AFTER = observed(local("main"), remote("main"), fetched_at=FRESH_FETCH)


class RecordingFetcher:
    """A fetcher that records every anchor and answers a scripted report."""

    def __init__(self, *reports: FetchReport | Exception) -> None:
        self.reports = list(reports)
        self.anchors: list[Path] = []
        self.release = Event()
        self.release.set()

    def __call__(self, anchor: Path) -> FetchReport:
        self.anchors.append(anchor)
        self.release.wait(timeout=2)
        report = self.reports.pop(0) if self.reports else success(anchor)
        if isinstance(report, Exception):
            raise report
        return report


def success(anchor: Path, *remotes: str) -> FetchReport:
    return FetchReport(
        str(anchor), tuple(RemoteFetch(name, True) for name in remotes or ("origin",))
    )


def branch_names(app: DashpotApp) -> list[str]:
    return sorted(row.name for row in app.store.query_branches().rows)


def remote_branch_names(app: DashpotApp) -> list[str]:
    return sorted(row.name for row in app.store.query_branches().rows if row.remotes)


def diagnostics_text(app: DashpotApp) -> str:
    return str(app.query_one("#diagnostics", Static).render())


def toasts(app: DashpotApp) -> list[str]:
    return [notification.message for notification in app._notifications]


@pytest.mark.asyncio
async def test_f_fetches_and_prunes_every_remote_then_observes_the_result() -> None:
    # The fake Git seam: a real fetch over scripted Git answers, so the exact
    # invocation is asserted, and the observation after it lacks the pruned
    # Remote-Tracking Branch and carries the new fetch age.
    runner = SequenceRunner(
        completed("origin\nupstream\n"), completed(""), completed("")
    )
    git = Git(Path("/unused"), runner=runner)
    collector = SequenceCollector(BEFORE, AFTER)
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        fetcher=lambda anchor: fetch_remotes(anchor, git=git),
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        assert remote_branch_names(app) == ["feature", "main"]
        assert pane_subtitle(app, "#branches-pane").endswith(
            "remote last fetched 3h ago"
        )
        assert collector.calls == 1

        await pilot.press("f")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()

        assert [call[0] for call in runner.calls] == [
            ["git", "remote"],
            ["git", "fetch", "--prune", "--", "origin"],
            ["git", "fetch", "--prune", "--", "upstream"],
        ]
        assert {call[1] for call in runner.calls} == {Path(ANCHOR)}
        assert collector.calls == 2
        assert remote_branch_names(app) == ["main"]
        assert pane_subtitle(app, "#branches-pane").endswith(
            "remote last fetched just now"
        )
        assert toasts(app) == ["Test Repository: fetched and pruned origin, upstream"]
        assert app.fetch_errors == {}
        assert not app.fetching


@pytest.mark.asyncio
async def test_only_the_clone_that_supplied_the_branches_is_fetched() -> None:
    fetcher = RecordingFetcher()
    before = observed(
        local("main"),
        remote("main"),
        branch_anchor="/clones/second",
        anchors=("/clones/first", "/clones/second"),
    )
    app = DashpotApp(
        SequenceCollector(before, before), refresh_seconds=0, fetcher=fetcher
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await wait_until(lambda: app.store.revision == 2)

        assert fetcher.anchors == [Path("/clones/second")]


@pytest.mark.asyncio
async def test_no_remote_is_refused_visibly_and_nothing_is_re_observed() -> None:
    runner = SequenceRunner(completed(""))
    git = Git(Path("/unused"), runner=runner)
    collector = SequenceCollector(BEFORE)
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        fetcher=lambda anchor: fetch_remotes(anchor, git=git),
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await wait_until(lambda: bool(app.fetch_errors))
        await pilot.pause()

        assert toasts(app) == ["Test Repository: no remote is configured"]
        assert "✖ Fetch failed: Test Repository: no remote is configured" in (
            diagnostics_text(app)
        )
        assert collector.calls == 1
        assert remote_branch_names(app) == ["feature", "main"]
        assert pane_subtitle(app, "#branches-pane").endswith(
            "remote last fetched 3h ago"
        )


@pytest.mark.asyncio
async def test_a_failed_remote_keeps_the_last_good_observation_and_says_why() -> None:
    # Authentication fails on one remote and the other times out: nothing was
    # fetched, so the pane is left exactly as observed and the failure names
    # both remotes.
    runner = SequenceRunner(
        completed("origin\nfork\n"),
        completed(
            "", stderr="fatal: Authentication failed for 'https://x'", returncode=128
        ),
        RuntimeError("command timed out after 10s: git"),
    )
    git = Git(Path("/unused"), runner=runner)
    collector = SequenceCollector(BEFORE)
    app = DashpotApp(
        collector,
        refresh_seconds=0,
        fetcher=lambda anchor: fetch_remotes(anchor, git=git),
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await wait_until(lambda: bool(app.fetch_errors))
        await pilot.pause()

        assert app.fetch_errors == {
            "project:test-repo": (
                "Fetch failed: Test Repository: failed origin: fatal: Authentication "
                "failed for 'https://x'; fork: command timed out after 10s: git"
            )
        }
        assert collector.calls == 1
        assert remote_branch_names(app) == ["feature", "main"]
        assert pane_subtitle(app, "#branches-pane").endswith(
            "remote last fetched 3h ago"
        )


@pytest.mark.asyncio
async def test_a_partial_fetch_is_reported_as_a_failure_but_still_observed() -> None:
    fetcher = RecordingFetcher(
        FetchReport(
            ANCHOR,
            (RemoteFetch("origin", True), RemoteFetch("fork", False, "ssh: no route")),
        )
    )
    collector = SequenceCollector(BEFORE, AFTER)
    app = DashpotApp(collector, refresh_seconds=0, fetcher=fetcher)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await wait_until(lambda: app.store.revision == 2)
        await pilot.pause()

        # What origin delivered is observed, but the fork's failure is not
        # hidden behind it.
        assert remote_branch_names(app) == ["main"]
        assert toasts(app) == [
            "Test Repository: fetched and pruned origin; failed fork: ssh: no route"
        ]
        assert "✖ Fetch failed: Test Repository" in diagnostics_text(app)

        # The next clean fetch clears the failure.
        collector.results.append(AFTER)
        await pilot.press("f")
        await wait_until(lambda: app.store.revision == 3)
        await pilot.pause()
        assert app.fetch_errors == {}
        assert "Fetch failed" not in diagnostics_text(app)


@pytest.mark.asyncio
async def test_repeated_presses_do_not_overlap_and_the_fetch_is_visible() -> None:
    fetcher = RecordingFetcher()
    fetcher.release.clear()
    collector = SequenceCollector(BEFORE, AFTER)
    app = DashpotApp(collector, refresh_seconds=0, fetcher=fetcher)

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await wait_until(lambda: app.store.revision == 1)
            await pilot.press("f")
            await wait_until(lambda: len(fetcher.anchors) == 1)
            await pilot.pause()
            alert = app.query_one("#alert", Static)
            assert alert.has_class("-visible")
            assert str(alert.render()) == "↻ fetching remotes Test Repository"

            await pilot.press("f")
            await pilot.pause()
            assert toasts(app) == ["Already fetching Test Repository"]
            assert len(fetcher.anchors) == 1

            fetcher.release.set()
            await wait_until(lambda: app.store.revision == 2)
            await pilot.pause()
            assert not alert.has_class("-visible")
            assert not app.fetching
    finally:
        fetcher.release.set()


@pytest.mark.asyncio
async def test_a_fetcher_crash_is_a_visible_failure_not_an_exit() -> None:
    fetcher = RecordingFetcher(OSError("git vanished"))
    app = DashpotApp(SequenceCollector(BEFORE), refresh_seconds=0, fetcher=fetcher)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await wait_until(lambda: bool(app.fetch_errors))

        assert app.fetch_errors == {
            "project:test-repo": "Fetch failed: Test Repository: git vanished"
        }
        assert not app.fetching


@pytest.mark.asyncio
async def test_f_is_refused_until_a_branch_observation_names_an_anchor() -> None:
    fetcher = RecordingFetcher()
    app = DashpotApp(
        SequenceCollector(observed(local("main"), branch_anchor=None)),
        refresh_seconds=0,
        fetcher=fetcher,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await pilot.pause()

        assert fetcher.anchors == []
        assert toasts(app) == [
            "No Branch observation names a Repository Anchor to fetch yet"
        ]


@pytest.mark.asyncio
async def test_a_view_without_a_fetcher_refuses_the_key() -> None:
    app = DashpotApp(SequenceCollector(BEFORE), refresh_seconds=0)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.press("f")
        await pilot.pause()

        assert toasts(app) == ["Fetching is not available in this view"]


@pytest.mark.asyncio
async def test_startup_and_refresh_never_fetch() -> None:
    fetcher = RecordingFetcher()
    collector = SequenceCollector(BEFORE, BEFORE, BEFORE)
    app = DashpotApp(collector, refresh_seconds=0.05, fetcher=fetcher)

    async with app.run_test(size=(120, 40)):
        await wait_until(lambda: app.store.revision == 1)
        await app.run_action("refresh")
        await wait_until(lambda: collector.calls >= 3)

        assert fetcher.anchors == []


@pytest.mark.asyncio
async def test_f_is_listed_in_the_footer_and_the_legend() -> None:
    app = DashpotApp(
        SequenceCollector(BEFORE), refresh_seconds=0, fetcher=RecordingFetcher()
    )

    async with app.run_test(size=(160, 40)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        assert "f" in footer_keys(app)
        footer = app.query_one(Footer)
        assert ("f", "Fetch & prune remotes") in [
            (key.key, key.description) for key in footer.query(FooterKey)
        ]

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, LegendScreen)
        assert "Fetch & prune remotes" in str(
            app.screen.query_one("#legend-keys", Static).render()
        )
