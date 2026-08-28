from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Callable

import pytest

from dashpot.collect import (
    AGENT_RUNS_KEY,
    ObservationCoordinator,
    ObservationKey,
    SnapshotScheduler,
)
from dashpot.issue_sources import IssueSource
from dashpot.model import (
    AgentRun,
    ObservationTarget,
    ObservationTargetInventory,
    ResolvedProject,
    WorkspaceSnapshot,
)
from dashpot.observation_store import StoreChange, WorkspaceObservationStore


ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def issue(reference: str, project_id: str) -> dict:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["reference"] = reference
    value["id"] = f"I_{reference}"
    value["number"] = int(reference.rpartition("#")[2])
    value["projectId"] = project_id
    value["title"] = f"Issue {reference}"
    return value


def target(root: Path, head: str = "abc123") -> ObservationTarget:
    return ObservationTarget(
        str(root), head, "main", False, False, "available", 1, []
    )


class ScriptedSource(IssueSource):
    """An Issue Source whose collections are scripted and observable."""

    def __init__(self, project_id: str, *, clock=None) -> None:
        super().__init__(clock=clock)
        self.project_id = project_id
        self.collections: list[list[dict] | Exception] = []
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"scripted:{self.project_id}"

    def _collect(self) -> list[dict]:
        with self.lock:
            self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        if not self.collections:
            return [issue(f"{self.project_id}#1", self.project_id)]
        result = self.collections.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class ScriptedCollector:
    def __init__(self, source: ScriptedSource, root: Path) -> None:
        self.source = source
        self.root = root
        self.target_failures: list[Exception] = []
        self.target_calls = 0
        self.targets_release = threading.Event()
        self.targets_release.set()
        self.head = "abc123"

    def observe_issues(self):
        return self.source.refresh()

    def observe_targets(self) -> ObservationTargetInventory:
        self.target_calls += 1
        self.targets_release.wait(timeout=2)
        if self.target_failures:
            raise self.target_failures.pop(0)
        return ObservationTargetInventory([target(self.root, self.head)], [])


class Clock:
    def __init__(self) -> None:
        self.tick = 0
        self.lock = threading.Lock()

    def __call__(self) -> str:
        with self.lock:
            self.tick += 1
            return f"2026-08-28T00:00:{self.tick:02d}Z"


def resolved(root: Path, project_id: str) -> ResolvedProject:
    return ResolvedProject(
        project_id, project_id.title(), f"repository:{project_id}", ("test",),
        (str(root),), str(root),
    )


@pytest.fixture
def workspace(tmp_path: Path):
    """Two configured Projects with scripted sources and a shared clock."""
    clock = Clock()
    projects: list[ResolvedProject] = []
    collectors: dict[str, ScriptedCollector] = {}
    for name in ("alpha", "beta"):
        root = tmp_path / name
        root.mkdir()
        projects.append(resolved(root, name))
        collectors[name] = ScriptedCollector(ScriptedSource(name, clock=clock), root)
    runs: list[AgentRun] = []
    observed_targets: list[dict] = []

    def agent_observer(targets_by_project):
        observed_targets.append(dict(targets_by_project))
        return list(runs), []

    coordinator = ObservationCoordinator(
        projects,
        factory=lambda project, **_kwargs: collectors[project.project_id],
        agent_observer=agent_observer,
        clock=clock,
    )
    return coordinator, collectors, runs, observed_targets


def observe_all(coordinator: ObservationCoordinator, project_id: str | None = None):
    for ticket in coordinator.request(coordinator.keys(project_id)):
        coordinator.observe(ticket)


def project_ids(store: WorkspaceObservationStore) -> list[str]:
    return [project.project_id for project in store.checkpoint().projects]


def test_keys_select_one_project_or_the_whole_workspace(workspace) -> None:
    coordinator, _collectors, _runs, _targets = workspace

    assert coordinator.keys("beta") == [
        ObservationKey("issues", "beta"),
        ObservationKey("targets", "beta"),
        AGENT_RUNS_KEY,
    ]
    assert coordinator.keys() == [
        ObservationKey("issues", "alpha"),
        ObservationKey("targets", "alpha"),
        ObservationKey("issues", "beta"),
        ObservationKey("targets", "beta"),
        AGENT_RUNS_KEY,
    ]
    assert coordinator.keys("unknown") == coordinator.keys()
    projects_changed = StoreChange(
        1, frozenset({"projects"}), frozenset(), frozenset(), frozenset(), frozenset()
    )
    runs_changed = StoreChange(
        2, frozenset({"agent-runs"}), frozenset(), frozenset(), frozenset(), frozenset()
    )
    assert coordinator.follow_ups([runs_changed, projects_changed]) == [AGENT_RUNS_KEY]
    assert coordinator.follow_ups([runs_changed]) == []


def test_project_is_published_only_after_both_halves_are_observed(
    workspace,
) -> None:
    coordinator, _collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    issues, targets = coordinator.request(
        [ObservationKey("issues", "alpha"), ObservationKey("targets", "alpha")]
    )

    assert coordinator.observe(issues).accepted
    assert coordinator.publish(store) == []
    assert not store.has_observations

    assert coordinator.observe(targets).accepted
    changes = coordinator.publish(store)

    assert [change.kinds for change in changes] == [frozenset({"projects", "workspace"})]
    assert project_ids(store) == ["alpha"]
    project = store.project("alpha")
    assert project is not None and project.snapshot is not None
    assert project.snapshot.issue_source_status == "fresh"
    assert project.snapshot.target_status == "fresh"
    assert [item["id"] for item in project.snapshot.issues] == ["I_alpha#1"]
    assert coordinator.publish(store) == []


def test_targets_land_independently_of_a_slow_issue_source(workspace) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    observe_all(coordinator)
    coordinator.publish(store)
    alpha = collectors["alpha"]
    alpha.head = "def456"
    alpha.source.release.clear()
    alpha.source.started.clear()
    issues, targets = coordinator.request(
        [ObservationKey("issues", "alpha"), ObservationKey("targets", "alpha")]
    )
    slow = threading.Thread(target=coordinator.observe, args=(issues,))
    slow.start()
    try:
        assert alpha.source.started.wait(timeout=2)

        assert coordinator.observe(targets).accepted
        changes = coordinator.publish(store)

        assert len(changes) == 1
        project = store.project("alpha")
        assert project is not None and project.snapshot is not None
        assert project.snapshot.observation_targets[0].head == "def456"
        assert project.snapshot.target_attempted_at is not None
        assert project.snapshot.target_attempted_at > (
            project.snapshot.issue_source_attempted_at
        )
    finally:
        alpha.source.release.set()
        slow.join(timeout=2)


def test_superseded_ticket_cannot_overwrite_the_newer_result(workspace) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    observe_all(coordinator)
    coordinator.publish(store)
    alpha = collectors["alpha"]
    alpha.source.collections = [
        [issue("alpha#1", "alpha")],
        [issue("alpha#2", "alpha")],
    ]
    alpha.source.release.clear()
    alpha.source.started.clear()
    key = ObservationKey("issues", "alpha")
    (old,) = coordinator.request([key])
    outcomes = []
    stale = threading.Thread(
        target=lambda: outcomes.append(coordinator.observe(old))
    )
    stale.start()
    try:
        assert alpha.source.started.wait(timeout=2)
        (new,) = coordinator.request([key])
        assert not coordinator.is_current(old)
        fresh = threading.Thread(
            target=lambda: outcomes.append(coordinator.observe(new))
        )
        fresh.start()
        alpha.source.release.set()
        stale.join(timeout=2)
        fresh.join(timeout=2)
    finally:
        alpha.source.release.set()

    by_generation = {outcome.ticket.generation: outcome for outcome in outcomes}
    assert not by_generation[old.generation].accepted
    assert by_generation[new.generation].accepted
    coordinator.publish(store)
    project = store.project("alpha")
    assert project is not None and project.snapshot is not None
    assert [item["id"] for item in project.snapshot.issues] == ["I_alpha#2"]


def test_cancelled_ticket_is_skipped_without_touching_the_source(
    workspace,
) -> None:
    coordinator, collectors, _runs, _targets = workspace
    key = ObservationKey("issues", "alpha")
    (old,) = coordinator.request([key])
    (new,) = coordinator.request([key])

    outcome = coordinator.observe(old)

    assert not outcome.accepted
    assert collectors["alpha"].source.calls == 0
    assert coordinator.observe(new).accepted
    assert collectors["alpha"].source.calls == 1


def test_target_failure_keeps_last_good_targets_and_fresh_issues(
    workspace,
) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    observe_all(coordinator)
    coordinator.publish(store)
    first = store.project("alpha")
    assert first is not None and first.snapshot is not None
    good_at = first.snapshot.target_last_good_at
    collectors["alpha"].target_failures = [RuntimeError("git exploded")]

    observe_all(coordinator, "alpha")
    coordinator.publish(store)

    project = store.project("alpha")
    assert project is not None and project.snapshot is not None
    assert project.status == "fresh"
    assert project.snapshot.issue_source_status == "fresh"
    assert project.snapshot.target_status == "stale"
    assert project.snapshot.target_last_good_at == good_at
    assert project.snapshot.target_attempted_at is not None
    assert project.snapshot.target_attempted_at > good_at
    assert [item.path for item in project.snapshot.observation_targets] == [
        str(collectors["alpha"].root)
    ]
    assert [item.code for item in project.snapshot.diagnostics] == [
        "target-discovery"
    ]
    assert "git exploded" in project.snapshot.diagnostics[0].message


def test_issue_failure_keeps_last_good_issues_and_fresh_targets(
    workspace,
) -> None:
    from dashpot.issue_sources import IssueSourceRefreshError

    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    observe_all(coordinator)
    coordinator.publish(store)
    collectors["alpha"].source.collections = [
        IssueSourceRefreshError("github-down", "GitHub is unavailable")
    ]
    collectors["alpha"].head = "fresh00"

    observe_all(coordinator, "alpha")
    coordinator.publish(store)

    project = store.project("alpha")
    assert project is not None and project.snapshot is not None
    assert project.status == "stale"
    assert project.snapshot.issue_source_status == "stale"
    assert project.snapshot.target_status == "fresh"
    assert project.snapshot.observation_targets[0].head == "fresh00"
    assert [item["id"] for item in project.snapshot.issues] == ["I_alpha#1"]
    assert project.snapshot.issue_source_last_good_at is not None
    assert project.snapshot.issue_source_last_good_at < (
        project.snapshot.issue_source_attempted_at
    )


def test_project_failure_after_success_retains_both_halves_once(
    workspace, tmp_path: Path
) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    observe_all(coordinator)
    coordinator.publish(store)
    collectors["alpha"].root.rename(tmp_path / "moved")

    observe_all(coordinator, "alpha")
    coordinator.publish(store)

    project = store.project("alpha")
    assert project is not None and project.snapshot is not None
    assert project.status == "stale"
    assert project.snapshot.target_status == "stale"
    assert [item.code for item in project.diagnostics] == ["project-collection"]
    assert project.snapshot.issues and project.snapshot.observation_targets


def test_project_failure_without_history_is_unavailable(workspace, tmp_path) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    collectors["beta"].root.rename(tmp_path / "gone")

    observe_all(coordinator)
    coordinator.publish(store)

    beta = store.project("beta")
    assert beta is not None
    assert beta.status == "unavailable"
    assert beta.snapshot is None
    assert beta.diagnostics[0].code == "project-collection"
    alpha = store.project("alpha")
    assert alpha is not None and alpha.status == "fresh"


def test_current_project_refresh_leaves_other_projects_untouched(
    workspace,
) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()
    observe_all(coordinator)
    coordinator.publish(store)
    before = store.project("alpha")
    assert before is not None and before.snapshot is not None
    alpha_calls = collectors["alpha"].source.calls

    observe_all(coordinator, "beta")
    changes = coordinator.publish(store)

    assert {pid for change in changes for pid in change.project_ids} == {"beta"}
    assert collectors["alpha"].source.calls == alpha_calls
    assert collectors["beta"].source.calls == 2
    after = store.project("alpha")
    assert after is not None and after.snapshot is not None
    assert after.snapshot.collected_at == before.snapshot.collected_at


def test_workspace_fan_out_refreshes_every_project(workspace) -> None:
    coordinator, collectors, _runs, _targets = workspace
    store = WorkspaceObservationStore()

    observe_all(coordinator)
    changes = coordinator.publish(store)

    assert {pid for change in changes for pid in change.project_ids} == {
        "alpha",
        "beta",
    }
    assert [change.kinds for change in changes][-1] >= {"agent-runs"}
    assert all(c.source.calls == 1 for c in collectors.values())
    assert all(c.target_calls == 1 for c in collectors.values())


def test_agent_runs_observe_composed_targets_and_defer_pending_bindings(
    workspace,
) -> None:
    coordinator, collectors, runs, observed_targets = workspace
    store = WorkspaceObservationStore()
    runs.append(
        AgentRun(
            id="codex-session:one",
            harness="codex",
            process_or_session="codex pid 1",
            state="running",
            observation_target=str(collectors["beta"].root),
            observation_project_id="beta",
            branch="main",
            issue_id="I_beta#1",
            issue_reference_hint=None,
        )
    )
    for ticket in coordinator.request(coordinator.keys("alpha")):
        coordinator.observe(ticket)
    coordinator.publish(store)

    assert list(observed_targets[-1]) == ["alpha"]
    deferred = [d for d in store.checkpoint().diagnostics]
    assert [d.code for d in deferred] == ["agent-issue-resolution-deferred"]
    assert store.checkpoint().issue_runs == {"I_alpha#1": []}

    for ticket in coordinator.request(coordinator.keys("beta")):
        coordinator.observe(ticket)
    coordinator.publish(store)

    assert sorted(observed_targets[-1]) == ["alpha", "beta"]
    assert store.checkpoint().diagnostics == []
    assert store.checkpoint().issue_runs["I_beta#1"] == ["codex-session:one"]


def test_barrier_refresh_is_a_complete_checkpoint(workspace) -> None:
    coordinator, collectors, _runs, _targets = workspace
    collectors["beta"].source.release.clear()

    def release_beta_after_alpha() -> None:
        collectors["alpha"].source.started.wait(timeout=2)
        collectors["beta"].source.release.set()

    threading.Thread(target=release_beta_after_alpha).start()

    snapshot = coordinator.refresh()

    assert isinstance(snapshot, WorkspaceSnapshot)
    assert [project.project_id for project in snapshot.projects] == ["alpha", "beta"]
    assert all(project.status == "fresh" for project in snapshot.projects)
    assert snapshot.collected_at.startswith("2026-08-28")
    assert snapshot.elapsed_ms >= 0
    assert snapshot.issue_runs == {"I_alpha#1": [], "I_beta#1": []}
    # A second barrier is independent and still complete.
    again = coordinator.refresh()
    assert [project.project_id for project in again.projects] == ["alpha", "beta"]


def test_snapshot_scheduler_publishes_a_whole_checkpoint_once() -> None:
    snapshot = WorkspaceSnapshot("2026-08-28T00:00:00Z", 1, [])

    class Collector:
        def refresh(self) -> WorkspaceSnapshot:
            return snapshot

    scheduler = SnapshotScheduler(Collector())
    store = WorkspaceObservationStore()
    (old,) = scheduler.request(scheduler.keys())
    (new,) = scheduler.request(scheduler.keys())

    assert not scheduler.observe(old).accepted
    assert scheduler.publish(store) == []
    assert scheduler.observe(new).accepted
    assert len(scheduler.publish(store)) == 1
    assert scheduler.publish(store) == []
    assert store.checkpoint().collected_at == "2026-08-28T00:00:00Z"
