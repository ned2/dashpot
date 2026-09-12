"""Fetch from a Cleanup preview without authorizing or retargeting deletion."""

from pathlib import Path

import pytest
from textual.widgets import Button, Checkbox, Footer, Static
from typing_extensions import override

from app_harness import SequenceCollector, with_first_project_snapshot
from dashpot.app import DashpotApp
from dashpot.cleanup_view import CleanupScreen
from dashpot.fetch import FetchReport, RemoteFetch
from helpers import wait_until
from test_dashboard_cleanup import (
    ANCHOR,
    ATTACHED,
    BEFORE,
    BRANCH_KEY,
    BRANCH_PREVIEW,
    BRANCH_REQUEST,
    LOCAL,
    PROJECT,
    REMOTE,
    TREE,
    WORKTREE_KEY,
    WORKTREE_PREVIEW,
    WORKTREE_REQUEST,
    FakeCleaner,
    focus_row,
)
from test_dashboard_fetch import RecordingFetcher


async def open_preview(app, pilot, kind):
    await wait_until(lambda: app.store.revision == 1)
    await focus_row(
        app,
        pilot,
        "worktrees-pane" if kind == "worktree" else "branches-pane",
        WORKTREE_KEY if kind == "worktree" else BRANCH_KEY,
    )
    await pilot.press("x")
    await wait_until(lambda: isinstance(app.screen, CleanupScreen))
    return app.screen


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["worktree", "branch"])
async def test_fetch_stays_in_same_dialog_and_holds_confirmation(kind):
    preview = WORKTREE_PREVIEW if kind == "worktree" else BRANCH_PREVIEW
    request = WORKTREE_REQUEST if kind == "worktree" else BRANCH_REQUEST
    cleaner = FakeCleaner(preview, preview)
    fetcher = RecordingFetcher()
    fetcher.release.clear()
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=fetcher,
    )
    try:
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await open_preview(app, pilot, kind)
            assert "Press f here to fetch and prune remotes" in str(
                screen.query_one("#cleanup-freshness", Static).render()
            )
            assert screen.query_one(Footer)
            assert (
                screen.active_bindings["f"].binding.description
                == "Fetch & prune remotes"
            )
            await pilot.press("f")
            await wait_until(lambda: fetcher.anchors == [Path(ANCHOR)])
            assert screen.busy and screen.query_one("#cleanup-confirm", Button).disabled
            await pilot.press("f", "f")
            screen.action_confirm()
            assert not cleaner.confirmations
            assert len(fetcher.anchors) == 1
            app.dashboard.branches_pane().table.move_cursor(row=0)
            fetcher.release.set()
            await wait_until(lambda: not app.fetching and not screen.busy)
            assert app.screen is screen and screen.preview_valid
            assert cleaner.requests == [request, request]
            assert "fetched and pruned origin" in screen.fetch_status
            assert app.cleaning and not cleaner.confirmations
    finally:
        fetcher.release.set()


@pytest.mark.asyncio
async def test_fetch_preserves_unchanged_optional_choice_and_resets_acknowledgement():
    cleaner = FakeCleaner(WORKTREE_PREVIEW, WORKTREE_PREVIEW)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(120, 45)) as pilot:
        screen = await open_preview(app, pilot, "worktree")
        assert not screen.query("#cleanup-target-0")
        screen.query_one("#cleanup-target-1", Checkbox).value = True
        screen.query_one("#cleanup-ignored", Checkbox).value = True
        await pilot.pause()
        assert screen.selected() == (TREE.identity, ATTACHED.identity)
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert screen.selected() == (TREE.identity, ATTACHED.identity)
        assert not screen.ignored_acknowledged()
        assert (
            str(screen.query_one("#cleanup-confirm", Button).label)
            == "Remove Worktree and Branch"
        )


@pytest.mark.asyncio
async def test_fetch_drops_changed_optional_tip_and_never_selects_new_targets():
    available_remote = REMOTE.model_copy(update={"blockers": ()})
    initial = BRANCH_PREVIEW.model_copy(update={"targets": (LOCAL, available_remote)})
    changed = available_remote.model_copy(update={"expected": "new-tip"})
    extra = available_remote.model_copy(
        update={
            "identity": "remote:upstream:feat",
            "remote": "upstream",
            "label": "Branch at upstream",
        }
    )
    updated = initial.model_copy(
        update={"targets": (LOCAL, changed, extra), "fingerprint": "new"}
    )
    cleaner = FakeCleaner(initial, updated)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(120, 45)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        screen.query_one("#cleanup-target-1", Checkbox).value = True
        await pilot.pause()
        assert screen.selected() == (LOCAL.identity, available_remote.identity)
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert screen.primary_identity == LOCAL.identity
        assert screen.selected() == (LOCAL.identity,)
        assert "Preview updated" in screen.fetch_status
        assert not cleaner.confirmations


@pytest.mark.asyncio
async def test_fetch_dismissal_never_reopens_or_performs_cleanup():
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    fetcher = RecordingFetcher()
    fetcher.release.clear()
    collector = SequenceCollector(BEFORE, BEFORE)
    app = DashpotApp(collector, refresh_seconds=0, cleaner=cleaner, fetcher=fetcher)
    try:
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await open_preview(app, pilot, "branch")
            await pilot.press("f")
            await wait_until(lambda: bool(fetcher.anchors))
            await pilot.press("escape")
            await wait_until(lambda: app.screen is app.dashboard)
            assert not app.cleaning and app.fetching
            await pilot.press("x")
            assert app.screen is app.dashboard
            fetcher.release.set()
            await wait_until(lambda: not app.fetching)
            assert app.screen is app.dashboard and screen not in app.screen_stack
            assert len(cleaner.requests) == 1 and not cleaner.confirmations
            assert collector.calls == 2
    finally:
        fetcher.release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        FetchReport(
            ANCHOR,
            (RemoteFetch("origin", True), RemoteFetch("upstream", False, "denied")),
        ),
        FetchReport(ANCHOR, refusal="no remote is configured"),
        RuntimeError("network unavailable"),
    ],
)
async def test_failure_or_partial_fetch_stays_visible_with_fresh_inspection(answer):
    cleaner = FakeCleaner(BRANCH_PREVIEW, BRANCH_PREVIEW)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(answer),
    )
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert screen.preview_valid and not cleaner.confirmations
        assert (
            str(answer) if isinstance(answer, Exception) else answer.summary()
        ) in screen.fetch_status
        assert PROJECT in app.fetch_errors


@pytest.mark.asyncio
async def test_reinspection_failure_disables_confirmation_until_retry():
    cleaner = FakeCleaner(
        BRANCH_PREVIEW, RuntimeError("inspection denied"), BRANCH_PREVIEW
    )
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert not screen.preview_valid
        assert screen.query_one("#cleanup-confirm", Button).disabled
        assert "inspection denied" in screen.fetch_status
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 3 and not screen.busy)
        assert screen.preview_valid


@pytest.mark.asyncio
async def test_stale_post_fetch_observation_keeps_confirmation_unavailable():
    stale = with_first_project_snapshot(BEFORE, target_status="stale")
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = DashpotApp(
        SequenceCollector(BEFORE, stale),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        await pilot.press("f")
        await wait_until(
            lambda: app.store.revision == 2 and not screen.busy and not app.fetching
        )
        assert not screen.preview_valid
        assert len(cleaner.requests) == 1


@pytest.mark.asyncio
async def test_prefetch_observation_cannot_release_the_confirmation_barrier():
    from threading import Event

    class GatedCollector(SequenceCollector):
        def __init__(self):
            super().__init__(BEFORE, BEFORE, BEFORE)
            self.attempts = 0
            self.entered_old, self.release_old = Event(), Event()
            self.entered_new, self.release_new = Event(), Event()

        @override
        def refresh(self):
            self.attempts += 1
            if self.attempts == 2:
                self.entered_old.set()
                self.release_old.wait(timeout=5)
            elif self.attempts == 3:
                self.entered_new.set()
                self.release_new.wait(timeout=5)
            return super().refresh()

    collector = GatedCollector()
    cleaner = FakeCleaner(BRANCH_PREVIEW, BRANCH_PREVIEW)
    app = DashpotApp(
        collector, refresh_seconds=0, cleaner=cleaner, fetcher=RecordingFetcher()
    )
    try:
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await open_preview(app, pilot, "branch")
            app.schedule_observations(app.scheduler.keys(), "timer")
            await wait_until(collector.entered_old.is_set)
            await pilot.press("f")
            await wait_until(lambda: "Refreshing Git" in screen.fetch_status)
            collector.release_old.set()
            await wait_until(collector.entered_new.is_set)
            assert screen.busy and app.fetching
            assert len(cleaner.requests) == 1
            assert screen.query_one("#cleanup-confirm", Button).disabled
            collector.release_new.set()
            await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
            assert screen.preview_valid and not cleaner.confirmations
    finally:
        collector.release_old.set()
        collector.release_new.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["worktree", "branch"])
async def test_fetch_can_unblock_the_fixed_primary(kind):
    from dashpot.cleanup import CleanupBlocker

    ready = WORKTREE_PREVIEW if kind == "worktree" else BRANCH_PREVIEW
    ready = ready.model_copy(update={"ignored": ()})
    primary = ready.targets[0]
    blocked = primary.model_copy(
        update={
            "blockers": (CleanupBlocker(kind="unintegrated", detail="Fetch first"),)
        }
    )
    initial = ready.model_copy(update={"targets": (blocked,)})
    cleaner = FakeCleaner(initial, ready)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, kind)
        assert not screen.can_confirm and not screen.query("#cleanup-confirm")
        assert str(screen.query_one("#cleanup-cancel", Button).label) == "Close"
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert screen.primary_identity == primary.identity
        assert screen.selected() == (primary.identity,)
        assert not screen.query_one("#cleanup-confirm", Button).disabled
        assert not cleaner.confirmations


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["fetcher", "anchor"])
async def test_missing_fetch_support_leaves_preview_available(missing):
    snapshot = (
        with_first_project_snapshot(BEFORE, branch_anchor=None)
        if missing == "anchor"
        else BEFORE
    )
    cleaner = FakeCleaner(WORKTREE_PREVIEW)
    fetcher = RecordingFetcher()
    app = DashpotApp(
        SequenceCollector(snapshot),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=None if missing == "fetcher" else fetcher,
    )
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "worktree")
        await pilot.press("f")
        await wait_until(lambda: bool(screen.fetch_status))
        assert (
            "unavailable" in screen.fetch_status
            or "No Repository Anchor" in screen.fetch_status
        )
        assert not screen.busy and screen.preview_valid
        assert not fetcher.anchors and not cleaner.confirmations
        assert screen.selected() == (TREE.identity,)


@pytest.mark.asyncio
async def test_missing_primary_never_promotes_remaining_remote():
    remote = REMOTE.model_copy(update={"blockers": ()})
    initial = BRANCH_PREVIEW.model_copy(update={"targets": (LOCAL, remote)})
    refreshed = initial.model_copy(update={"targets": (remote,)})
    cleaner = FakeCleaner(initial, refreshed)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        screen.query_one("#cleanup-target-1", Checkbox).value = True
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert screen.primary_identity == LOCAL.identity
        assert not screen.can_confirm and screen.selected() == ()
        assert not screen.query("#cleanup-confirm")
        assert screen.query_one("#cleanup-target-0", Checkbox).disabled
        screen.action_confirm()
        assert not cleaner.confirmations


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_local", [False, True])
async def test_grouped_branch_targets_require_explicit_concrete_choices(blocked_local):
    from dashpot.cleanup import CleanupBlocker

    remote = REMOTE.model_copy(update={"blockers": ()})
    other = remote.model_copy(
        update={
            "identity": "remote:upstream:feat",
            "remote": "upstream",
            "label": "upstream/feat",
        }
    )
    local = LOCAL.model_copy(
        update={"blockers": (CleanupBlocker(kind="checked-out", detail="In use"),)}
    )
    targets = (local, remote) if blocked_local else (remote, other)
    preview = BRANCH_PREVIEW.model_copy(update={"targets": targets})
    cleaner = FakeCleaner(preview, preview)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        assert screen.primary_identity is None and screen.selected() == ()
        await pilot.press("space")
        assert screen.selected() == (remote.identity,)
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert screen.primary_identity is None and screen.selected() == (
            remote.identity,
        )
        assert not cleaner.confirmations


@pytest.mark.asyncio
async def test_partial_fetch_labels_repository_age_and_retained_remote_facts():
    from dashpot.cleanup_view import CleanupTargetView

    timestamp = "2026-09-12T00:00:00+00:00"
    origin = REMOTE.model_copy(update={"blockers": (), "observed_at": timestamp})
    upstream = origin.model_copy(
        update={"identity": "remote:upstream:feat", "remote": "upstream"}
    )
    preview = BRANCH_PREVIEW.model_copy(update={"targets": (LOCAL, origin, upstream)})
    cleaner = FakeCleaner(preview, preview)
    report = FetchReport(
        ANCHOR, (RemoteFetch("origin", True), RemoteFetch("upstream", False, "denied"))
    )
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(report),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        views = list(screen.query(CleanupTargetView))
        assert not views[1].unverified_remote and views[2].unverified_remote
        evidence = "\n".join(str(item.render()) for item in screen.query(Static))
        assert "Repository fetch timestamp:" in evidence
        assert "not per-remote verification" in evidence
        assert "did not verify upstream" in evidence
        assert (
            "Last fetched:" not in evidence and "as of the last fetch" not in evidence
        )
        assert screen.query_one("#cleanup-confirm", Button).region.bottom <= 24
        assert screen.query_one(Footer).region.bottom <= 24


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True])
async def test_worktree_fetch_age_covers_detached_and_independent_branch_blockers(
    detached,
):
    from dashpot.cleanup import CleanupBlocker

    branch = ATTACHED.model_copy(
        update={
            "blockers": (
                CleanupBlocker(kind="unintegrated", detail="Branch commits remain"),
            )
        }
    )
    preview = WORKTREE_PREVIEW.model_copy(
        update={"targets": (TREE,) if detached else (TREE, branch), "ignored": ()}
    )
    snapshot = with_first_project_snapshot(
        BEFORE, fetched_at="2026-09-11T00:00:00+00:00"
    )
    cleaner = FakeCleaner(preview)
    app = DashpotApp(SequenceCollector(snapshot), refresh_seconds=0, cleaner=cleaner)
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "worktree")
        guidance = str(screen.query_one("#cleanup-freshness", Static).render())
        assert "Press f here" in guidance and "2026-09-11" in guidance
        assert screen.selected() == (TREE.identity,)
        if detached:
            assert not screen.query("#cleanup-target-1")
        else:
            assert screen.query_one("#cleanup-target-1", Checkbox).disabled
        assert (
            str(screen.query_one("#cleanup-confirm", Button).label) == "Remove Worktree"
        )


@pytest.mark.asyncio
async def test_fetch_resets_acknowledgement_when_ignored_inventory_changes():
    updated = WORKTREE_PREVIEW.model_copy(
        update={"ignored": ("new-secret/",), "fingerprint": "changed"}
    )
    cleaner = FakeCleaner(WORKTREE_PREVIEW, updated)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "worktree")
        screen.query_one("#cleanup-ignored", Checkbox).value = True
        await pilot.press("f")
        await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
        assert not screen.ignored_acknowledged()
        assert "new-secret/" in str(
            screen.query_one("#cleanup-path-list", Static).render()
        )
        assert "Acknowledge" in screen.selection_problem()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_post_fetch_observation_failure_never_reenables_old_preview(failure):
    from threading import Event

    class FailingCollector(SequenceCollector):
        def __init__(self):
            super().__init__(BEFORE, BEFORE)
            self.release_observation = Event()

        @override
        def refresh(self):
            if self.calls:
                if failure == "error":
                    raise RuntimeError("observation denied")
                self.release_observation.wait(timeout=5)
            return super().refresh()

    collector = FailingCollector()
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = DashpotApp(
        collector, refresh_seconds=0, cleaner=cleaner, fetcher=RecordingFetcher()
    )
    app.cleanup_refresh_timeout = 0.05
    try:
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await open_preview(app, pilot, "branch")
            await pilot.press("f")
            await wait_until(lambda: not screen.busy and not app.fetching)
            assert not screen.preview_valid
            assert screen.query_one("#cleanup-confirm", Button).disabled
            assert "Could not refresh" in screen.fetch_status
            collector.release_observation.set()
            await app.workers.wait_for_complete()
            assert not screen.preview_valid and len(cleaner.requests) == 1
            assert not cleaner.confirmations
    finally:
        collector.release_observation.set()


@pytest.mark.asyncio
async def test_dismissal_during_recomposition_does_not_reopen_preview(monkeypatch):
    import asyncio

    cleaner = FakeCleaner(BRANCH_PREVIEW, BRANCH_PREVIEW)
    app = DashpotApp(
        SequenceCollector(BEFORE, BEFORE),
        refresh_seconds=0,
        cleaner=cleaner,
        fetcher=RecordingFetcher(),
    )
    entered, release = asyncio.Event(), asyncio.Event()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_preview(app, pilot, "branch")
        recompose = screen.recompose

        async def gated_recompose():
            entered.set()
            await release.wait()
            await recompose()

        monkeypatch.setattr(screen, "recompose", gated_recompose)
        await pilot.press("f")
        await entered.wait()
        await pilot.press("escape")
        release.set()
        await wait_until(lambda: not app.fetching)
        assert app.screen is app.dashboard and not app.cleaning
        assert not cleaner.confirmations


@pytest.mark.asyncio
async def test_paged_dashboard_fetch_waits_for_its_target_observation(tmp_path):
    from threading import Event

    from dashpot.model import RepositoryStateInventory
    from factories import target
    from test_paged_app import LocalOnlyCollector, application

    class Collector(LocalOnlyCollector):
        def __init__(self):
            self.calls = 0
            self.entered, self.release_observation = Event(), Event()

        @override
        def observe_targets(self):
            self.calls += 1
            if self.calls == 2:
                self.entered.set()
                self.release_observation.wait(timeout=5)
            return RepositoryStateInventory(
                targets=(
                    target(ANCHOR),
                    target(str(TREE.path), role="linked", branch="feat"),
                ),
                diagnostics=(),
                branch_anchor=ANCHOR,
                fetched_at="2026-09-12T00:00:00+00:00",
            )

    collector = Collector()
    cleaner = FakeCleaner(WORKTREE_PREVIEW, WORKTREE_PREVIEW)
    app = application(tmp_path, collector=collector)
    app.cleaner, app.fetcher = cleaner, RecordingFetcher()
    try:
        async with app.run_test(size=(100, 35)) as pilot:
            table = app.dashboard.worktrees_pane().table
            await wait_until(lambda: table.row_count == 2)
            row = next(
                row
                for row in app.store.query_worktrees().rows
                if row.target.path == TREE.path
            )
            selected = table.get_row_index(row.key)
            table.focus()
            table.move_cursor(row=selected)
            await pilot.press("x")
            await wait_until(lambda: isinstance(app.screen, CleanupScreen))
            screen = app.screen
            await pilot.press("f")
            await wait_until(collector.entered.is_set)
            assert screen.busy and len(cleaner.requests) == 1
            assert screen.query_one("#cleanup-confirm", Button).disabled
            collector.release_observation.set()
            await wait_until(lambda: len(cleaner.requests) == 2 and not screen.busy)
            assert app.screen is screen and screen.preview_valid
            assert app.fetcher.anchors == [Path(ANCHOR)]
            assert "2026-09-12" in str(
                screen.query_one("#cleanup-freshness", Static).render()
            )
            assert not cleaner.confirmations
    finally:
        collector.release_observation.set()
