"""The Remote Fetch flow holds each Project through its fetch, without an app."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from textual.message import Message

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
from dashpot.core.model import Branch, WorkspaceSnapshot
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.repository.fetch import FetchReport, RemoteFetch
from dashpot.ui.fetch_flow import RemoteFetchFlow
from dashpot.ui.messages import FetchFinished
from dashpot.ui.observation_runner import ObservationRunner

ANCHOR = "/repo"
LABEL = "Test Repository"


@dataclass
class OffLoopCall:
    """One operation the flow asked the host to run, held until landed."""

    name: str
    group: str
    operation: Callable[[], object]
    on_done: Callable[[object | None, str | None], Message]

    def land(self, *, error: str | None = None) -> FetchFinished:
        """Run the fetch, or fail it, and build the message it would post."""
        message = (
            self.on_done(None, error)
            if error is not None
            else self.on_done(self.operation(), None)
        )
        assert isinstance(message, FetchFinished)
        return message


class FakeTimer:
    def stop(self) -> None:
        pass


@dataclass
class FakeHost:
    """Record what a flow asks for; nothing runs until a test lands it."""

    calls: list[OffLoopCall] = field(default_factory=list)
    toasts: list[tuple[str, str, str]] = field(default_factory=list)
    alerts: int = 0
    diagnostics: int = 0
    closing: bool = False

    def run_off_loop(
        self,
        name: str,
        group: str,
        operation: Callable[[], object],
        on_done: Callable[[object | None, str | None], Message],
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.calls.append(OffLoopCall(name, group, operation, on_done))

    def set_timer(
        self, delay: float, callback: Callable[[], None], *, name: str | None = None
    ) -> FakeTimer:
        return FakeTimer()

    def notify(
        self, message: str, *, title: str = "", severity: str = "information"
    ) -> None:
        self.toasts.append((severity, title, message))

    def update_alert(self) -> None:
        self.alerts += 1

    def update_diagnostics(self) -> None:
        self.diagnostics += 1

    def pop_call(self, group: str) -> OffLoopCall:
        """Take the one started operation in ``group``."""
        matching = [call for call in self.calls if call.group == group]
        assert len(matching) == 1, [call.group for call in self.calls]
        self.calls.remove(matching[0])
        return matching[0]

    def observed_groups(self) -> list[str]:
        return [call.group for call in self.calls if call.group == WORKSPACE_KEY.group]


def observed(branch_anchor: str | None = ANCHOR) -> WorkspaceSnapshot:
    branch = Branch(
        refname="refs/heads/main",
        name="main",
        remote=None,
        head="aaa",
        committed_at="2026-08-25T00:00:00Z",
        upstream="origin/main",
    )
    snapshot = with_first_project_snapshot(
        workspace_snapshot(issue("test/repo#1", "First")),
        branches=[branch],
        integration_ref="refs/remotes/origin/main",
        branch_anchor=branch_anchor,
    )
    return with_first_project(snapshot, anchors=(ANCHOR,), primary_anchor=ANCHOR)


def success(anchor: Path) -> FetchReport:
    return FetchReport(str(anchor), (RemoteFetch("origin", True),))


def flow(
    fetcher: Callable[[Path], FetchReport] | None = success,
    snapshot: WorkspaceSnapshot | None = None,
) -> tuple[RemoteFetchFlow, FakeHost]:
    snapshot = snapshot or observed()
    store = PagedObservationStore(snapshot)
    host = FakeHost()
    observations = ObservationRunner(
        SnapshotScheduler(SequenceCollector(snapshot)), store, host
    )
    return RemoteFetchFlow(fetcher, store, observations, host), host


def test_the_key_is_refused_without_a_fetcher() -> None:
    fetches, host = flow(fetcher=None)
    fetches.request(held=())
    assert host.toasts == [
        ("warning", "Dashpot fetch", "Fetching is not available in this view")
    ]
    assert not host.calls


def test_the_key_is_refused_until_a_branch_observation_names_an_anchor() -> None:
    fetches, host = flow(snapshot=observed(branch_anchor=None))
    fetches.request(held=())
    assert host.toasts == [
        (
            "warning",
            "Dashpot fetch",
            "No Branch observation names a Repository Anchor to fetch yet",
        )
    ]
    assert not host.calls


def test_a_project_a_cleanup_holds_is_refused_until_it_finishes() -> None:
    fetches, host = flow()
    fetches.request(held={PROJECT_ID})
    assert host.toasts == [
        ("warning", "Dashpot fetch", f"Cleaning up {LABEL}; fetch after it finishes")
    ]
    assert not fetches.fetching
    assert not host.calls
    assert host.alerts == 1


def test_a_project_is_fetched_once_at_a_time() -> None:
    fetches, host = flow()
    fetches.request(held=())
    fetches.request(held=())
    assert fetches.fetching == {PROJECT_ID: ANCHOR}
    assert [call.group for call in host.calls] == [f"fetch:{PROJECT_ID}"]
    assert host.toasts == [("warning", "Dashpot fetch", f"Already fetching {LABEL}")]


def test_a_landed_fetch_releases_the_project_and_reobserves_its_git_facts() -> None:
    anchors: list[Path] = []

    def fetcher(anchor: Path) -> FetchReport:
        anchors.append(anchor)
        return success(anchor)

    fetches, host = flow(fetcher=fetcher)
    fetches.request(held=())
    fetches.record(host.pop_call(f"fetch:{PROJECT_ID}").land())
    assert anchors == [Path(ANCHOR)]
    assert not fetches.fetching
    assert not fetches.errors
    assert host.toasts == [
        ("information", "Dashpot fetch", f"{LABEL}: fetched and pruned origin")
    ]
    assert host.diagnostics == 1
    assert host.observed_groups() == [WORKSPACE_KEY.group]


def test_a_failure_is_kept_until_a_fetch_there_succeeds() -> None:
    fetches, host = flow()
    fetches.request(held=())
    fetches.record(host.pop_call(f"fetch:{PROJECT_ID}").land(error="boom"))
    assert fetches.errors == {PROJECT_ID: f"Fetch failed: {LABEL}: boom"}
    assert host.toasts[-1] == ("error", "Dashpot fetch", f"{LABEL}: boom")
    assert not host.observed_groups()

    fetches.request(held=())
    fetches.record(host.pop_call(f"fetch:{PROJECT_ID}").land())
    assert not fetches.errors


def test_a_fetch_that_reached_no_remote_leaves_the_observation_alone() -> None:
    fetches, host = flow(
        fetcher=lambda anchor: FetchReport(str(anchor), refusal="no remote configured")
    )
    fetches.request(held=())
    fetches.record(host.pop_call(f"fetch:{PROJECT_ID}").land())
    assert fetches.errors == {
        PROJECT_ID: f"Fetch failed: {LABEL}: no remote configured"
    }
    assert not host.observed_groups()


def test_a_result_can_be_recorded_without_releasing_or_observing() -> None:
    # The Cleanup preview's fetch keeps its hold and observes on its own terms.
    fetches, host = flow()
    fetches.hold(PROJECT_ID, Path(ANCHOR))
    fetches.record(
        FetchFinished(PROJECT_ID, report=success(Path(ANCHOR))),
        release=False,
        observe=False,
    )
    assert fetches.fetching == {PROJECT_ID: ANCHOR}
    assert not host.observed_groups()
    fetches.release(PROJECT_ID)
    assert not fetches.fetching


def test_an_outcome_after_shutdown_is_dropped() -> None:
    fetches, host = flow()
    fetches.request(held=())
    message = host.pop_call(f"fetch:{PROJECT_ID}").land()
    host.closing = True
    fetches.record(message)
    assert fetches.fetching == {PROJECT_ID: ANCHOR}
    assert not host.toasts
