"""The Cleanup flow holds each Project from preview to report, without an app.

The refusals and the late results are driven here; the preview, its fetch
and the confirmation need the modal, so ``test_dashboard_cleanup`` and
``test_cleanup_fetch`` drive those through the dashboard.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import factories
from app_harness import (
    PROJECT_ID,
    WORKSPACE_KEY,
    SequenceCollector,
    SnapshotScheduler,
    issue,
    with_first_project,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.cleanup import (
    BranchCleanupRequest,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    Outcome,
    TargetKind,
    TargetResult,
    WorktreeCleanupRequest,
)
from dashpot.cleanup_flow import (
    CleanupFlow,
    CleanupSelection,
    cleanup_result_line,
    cleanup_summary,
)
from dashpot.fetch_flow import RemoteFetchFlow
from dashpot.messages import CleanupFinished, CleanupInspected
from dashpot.model import Branch, WorkspaceSnapshot
from dashpot.observation_runner import ObservationRunner
from dashpot.paged_store import PagedObservationStore
from test_fetch_flow import FakeHost as FetchHost

ANCHOR = "/repo"
WORKTREE = "/repo.worktrees/feat"
LABEL = "Test Repository"
BRANCH_REQUEST = BranchCleanupRequest(Path(ANCHOR), "feat")
WORKTREE_REQUEST = WorktreeCleanupRequest(Path(ANCHOR), Path(WORKTREE))


@dataclass
class FakeHost(FetchHost):
    """The fetch host with the screens and workers a Cleanup asks for."""

    screen: Any = None
    screen_stack: list[Any] = field(default_factory=list)
    pushed: list[Any] = field(default_factory=list)

    def push_screen(self, screen: Any, callback: Any = None) -> object:
        self.pushed.append(screen)
        return screen

    def run_worker(
        self,
        work: Any,
        *,
        name: str | None = "",
        group: str = "default",
        exit_on_error: bool = True,
    ) -> object:
        raise AssertionError("no test here starts a preview fetch")

    async def off_loop(self, operation: Any) -> Any:
        return operation()


class FakeCleaner:
    """Record every inspection and performance; nothing here runs Git."""

    def __init__(self) -> None:
        self.inspected: list[CleanupRequest] = []

    def inspect(
        self, request: CleanupRequest, *, protected: Sequence[Path]
    ) -> CleanupPreview:
        self.inspected.append(request)
        return CleanupPreview(kind="branch", subject="feat", anchor=ANCHOR)

    def perform(
        self, confirmation: CleanupConfirmation, *, protected: Sequence[Path]
    ) -> CleanupReport:
        raise AssertionError("no test here performs a Cleanup")


def branch(name: str, *, remote: str | None = None) -> Branch:
    refname = f"refs/remotes/{remote}/{name}" if remote else f"refs/heads/{name}"
    return Branch(
        refname=refname,
        name=name,
        remote=remote,
        head="aaa",
        committed_at="2026-08-25T00:00:00Z",
        upstream=None if remote else f"origin/{name}",
    )


def observed(branch_anchor: str | None = ANCHOR) -> WorkspaceSnapshot:
    targets = (
        factories.target(ANCHOR),
        factories.target(WORKTREE, role="linked", branch="feat"),
    )
    snapshot = with_first_project_snapshot(
        workspace_snapshot(issue("test/repo#1", "First")),
        branches=[branch("main"), branch("feat"), branch("main", remote="origin")],
        observation_targets=targets,
        integration_ref="refs/remotes/origin/main",
        branch_anchor=branch_anchor,
    )
    return with_first_project(snapshot, anchors=(ANCHOR,), primary_anchor=ANCHOR)


def flow(
    cleaner: FakeCleaner | None = None, snapshot: WorkspaceSnapshot | None = None
) -> tuple[CleanupFlow, RemoteFetchFlow, PagedObservationStore, FakeHost]:
    snapshot = snapshot or observed()
    store = PagedObservationStore(snapshot)
    host = FakeHost()
    observations = ObservationRunner(
        SnapshotScheduler(SequenceCollector(snapshot)), store, host
    )
    fetches = RemoteFetchFlow(None, store, observations, host)
    cleanups = CleanupFlow(cleaner or FakeCleaner(), store, observations, fetches, host)
    return cleanups, fetches, store, host


def branch_selection(store: PagedObservationStore, name: str) -> CleanupSelection:
    rows = [row for row in store.query_branches().rows if row.name == name]
    assert len(rows) == 1, [row.name for row in store.query_branches().rows]
    return CleanupSelection("branch", rows[0].key)


def worktree_selection(store: PagedObservationStore, path: str) -> CleanupSelection:
    rows = [row for row in store.query_worktrees().rows if row.target.path == path]
    assert len(rows) == 1
    return CleanupSelection("worktree", rows[0].key)


def confirmation() -> CleanupConfirmation:
    return CleanupConfirmation(BRANCH_REQUEST, "f", ("branch:feat",))


def test_a_highlighted_branch_and_worktree_resolve_to_their_requests() -> None:
    cleanups, _fetches, store, host = flow()
    assert cleanups.resolve_request(branch_selection(store, "feat")) == (
        PROJECT_ID,
        BRANCH_REQUEST,
    )
    assert cleanups.resolve_request(worktree_selection(store, WORKTREE)) == (
        PROJECT_ID,
        WORKTREE_REQUEST,
    )
    cleanups.request(branch_selection(store, "feat"))
    assert cleanups.cleaning == {PROJECT_ID: "feat"}
    assert [call.group for call in host.calls] == [f"cleanup:{PROJECT_ID}"]


def test_a_row_no_longer_observed_is_refused() -> None:
    cleanups, _fetches, _store, host = flow()
    for selection in (
        CleanupSelection("branch", "gone"),
        CleanupSelection("worktree", "gone"),
    ):
        cleanups.request(selection)
    assert (
        host.toasts
        == [("warning", "Dashpot cleanup", "The highlighted row is no longer observed")]
        * 2
    )
    assert not cleanups.cleaning
    assert not host.calls


def test_a_branch_without_a_repository_anchor_is_refused() -> None:
    cleanups, _fetches, store, host = flow(snapshot=observed(branch_anchor=None))
    cleanups.request(branch_selection(store, "feat"))
    assert host.toasts == [
        ("warning", "Dashpot cleanup", "The highlighted row is no longer observed")
    ]
    assert not cleanups.cleaning


def test_a_project_being_fetched_is_refused() -> None:
    cleanups, fetches, store, host = flow()
    fetches.hold(PROJECT_ID, Path(ANCHOR))
    cleanups.request(branch_selection(store, "feat"))
    assert host.toasts == [
        ("warning", "Dashpot cleanup", f"Fetching {LABEL}; delete after it finishes")
    ]
    assert not cleanups.cleaning


def test_a_project_is_previewed_once_at_a_time() -> None:
    cleanups, _fetches, store, host = flow()
    cleanups.request(branch_selection(store, "feat"))
    cleanups.request(worktree_selection(store, WORKTREE))
    assert cleanups.cleaning == {PROJECT_ID: "feat"}
    assert [call.group for call in host.calls] == [f"cleanup:{PROJECT_ID}"]
    assert host.toasts == [
        ("warning", "Dashpot cleanup", f"Already cleaning up {LABEL}")
    ]


def test_a_late_inspection_after_shutdown_is_dropped() -> None:
    cleanups, _fetches, store, host = flow()
    cleanups.request(branch_selection(store, "feat"))
    host.closing = True
    cleanups.finish_inspection(
        CleanupInspected(PROJECT_ID, BRANCH_REQUEST, error="boom")
    )
    assert cleanups.cleaning == {PROJECT_ID: "feat"}
    assert not host.toasts


def test_confirming_while_a_fetch_runs_releases_the_project_instead() -> None:
    cleanups, fetches, store, host = flow()
    cleanups.request(branch_selection(store, "feat"))
    host.calls.clear()
    fetches.hold(PROJECT_ID, Path(ANCHOR))
    cleanups.confirm(PROJECT_ID, confirmation())
    assert not cleanups.cleaning
    assert not host.calls
    assert host.toasts == [
        (
            "warning",
            "",
            "Remote Fetch is still running; reopen Cleanup after it finishes.",
        )
    ]


def test_a_failed_cleanup_releases_the_project_and_reobserves_anyway() -> None:
    cleanups, _fetches, store, host = flow()
    cleanups.request(branch_selection(store, "feat"))
    host.calls.clear()
    cleanups.finish_cleanup(CleanupFinished(PROJECT_ID, confirmation(), error="boom"))
    assert not cleanups.cleaning
    assert host.toasts[-1] == ("error", "Dashpot cleanup", f"{LABEL}: boom")
    assert host.observed_groups() == [WORKSPACE_KEY.group]


def test_a_late_report_after_shutdown_is_dropped() -> None:
    cleanups, _fetches, store, host = flow()
    cleanups.request(branch_selection(store, "feat"))
    host.closing = True
    cleanups.finish_cleanup(CleanupFinished(PROJECT_ID, confirmation(), error="boom"))
    assert cleanups.cleaning == {PROJECT_ID: "feat"}
    assert not host.toasts


@pytest.mark.parametrize(
    ("kind", "outcome", "line"),
    [
        ("local-branch", "deleted", "Deleted feat"),
        ("worktree", "deleted", "Removed feat"),
        ("remote-branch", "already-absent", "feat already absent"),
        ("local-branch", "refused", "Refused feat"),
    ],
)
def test_each_outcome_has_its_toast_line(
    kind: TargetKind, outcome: Outcome, line: str
) -> None:
    result = TargetResult(
        identity=f"{kind}:feat",
        kind=kind,
        label="feat",
        expected="aaa",
        outcome=outcome,
        detail="",
    )
    assert cleanup_result_line(result) == line


def test_a_refused_report_summarises_its_refusals_and_nothing_else() -> None:
    shown = CleanupPreview(kind="branch", subject="feat", anchor=ANCHOR)
    refused = CleanupReport(
        kind="branch",
        subject="feat",
        anchor=ANCHOR,
        dry_run=False,
        performed=False,
        preview=shown,
        refusals=("feat moved after the preview", "origin/feat is protected"),
    )
    assert cleanup_summary(refused) == (
        "feat moved after the preview\norigin/feat is protected"
    )
