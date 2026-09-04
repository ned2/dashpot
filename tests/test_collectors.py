from __future__ import annotations

import contextlib
import copy
import json
import tempfile
import threading
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from typing_extensions import override

from dashpot.collect import ObservationCoordinator, ProjectCollector
from dashpot.commands import CommandResult
from dashpot.issue_profile import IssueProfile, conform_issue
from dashpot.issue_sources import (
    CollectedIssues,
    IssueSource,
    IssueSourceObservation,
)
from dashpot.model import (
    AgentRun,
    Branch,
    Diagnostic,
    IssueActivity,
    LinkedPullRequest,
    ObservationTarget,
    ProjectSnapshot,
    RepositoryStateInventory,
    ResolvedProject,
    WorkspaceSnapshot,
)
from dashpot.pull_request_sources import PullRequestSourceObservation
from dashpot.repository import BranchObservation, observe_github_repository_identity
from factories import observation_target
from helpers import jsonable

ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def target_inventory(root: str = "/repo") -> RepositoryStateInventory:
    return RepositoryStateInventory(targets=[observation_target(root)], diagnostics=[])


def resolved_project(
    root: str = "/repo", project_id: str = "project:example"
) -> ResolvedProject:
    return ResolvedProject(
        project_id,
        "Example",
        "repository:example",
        ("test",),
        (root,),
        root,
    )


def project_snapshot(
    root: str = "/repo",
    issues: list[IssueProfile] | None = None,
    *,
    project_id: str = "project:example",
) -> ProjectSnapshot:
    return ProjectSnapshot(
        project_id=project_id,
        display_label="Example",
        repository_id="repository:example",
        collected_at="2026-08-24T15:00:00Z",
        issue_source_status="fresh",
        issue_source_attempted_at="2026-08-24T15:00:00Z",
        issue_source_last_good_at="2026-08-24T15:00:00Z",
        observation_targets=[observation_target(root)],
        issues=[issue()] if issues is None else issues,
        diagnostics=[],
        pull_request_status="fresh",
        pull_request_attempted_at="2026-08-24T15:00:00Z",
        pull_request_last_good_at="2026-08-24T15:00:00Z",
    )


def issue_payload(reference: str = "example/project#7") -> dict[str, Any]:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["reference"] = reference
    value["id"] = f"I_{reference}"
    number_text = reference.rpartition("#")[2]
    if number_text.isdigit() and int(number_text) > 0:
        value["number"] = int(number_text)
    value["title"] = "Build observer"
    return value


def issue(reference: str = "example/project#7") -> IssueProfile:
    return conform_issue(issue_payload(reference))


class FakeSource(IssueSource):
    @property
    @override
    def name(self) -> str:
        return "fake"

    @override
    def _collect(self) -> CollectedIssues:
        return CollectedIssues((issue(),))


class EmptySource(IssueSource):
    @property
    @override
    def name(self) -> str:
        return "empty"

    @override
    def _collect(self) -> CollectedIssues:
        return CollectedIssues(())


class PaletteSource(FakeSource):
    @override
    def _collect(self) -> CollectedIssues:
        return CollectedIssues(
            issues=(issue(),),
            label_colors={"enhancement": "a2eeef"},
            issue_activity={
                issue().id: IssueActivity(
                    comment_count=2,
                    linked_pull_requests=[
                        LinkedPullRequest(
                            number=41,
                            url="https://example.test/pull/41",
                            state="merged",
                        )
                    ],
                )
            },
        )


class CountingSource(FakeSource):
    def __init__(self) -> None:
        super().__init__()
        self.collection_count = 0

    @override
    def _collect(self) -> CollectedIssues:
        self.collection_count += 1
        return super()._collect()


class RepositoryTests(unittest.TestCase):
    def test_github_repository_identity_uses_durable_node_id(self) -> None:
        calls: list[tuple[list[str], Path, float]] = []

        def runner(args, cwd, timeout):
            calls.append((list(args), cwd, timeout))
            return CommandResult(
                list(args),
                0,
                json.dumps({"node_id": "R_dashpot", "full_name": "ned2/dashpot"}),
                "",
            )

        result = observe_github_repository_identity(
            Path("/repo"), "ned2/dashpot", 7, runner
        )

        self.assertEqual(("R_dashpot", "ned2/dashpot"), result)
        self.assertEqual(
            [(["gh", "api", "repos/ned2/dashpot"], Path("/repo"), 7)],
            calls,
        )

    def test_identity_failures_carry_the_classified_code(self) -> None:
        cases = [
            (
                CommandResult(
                    [],
                    1,
                    '{"message":"Not Found","status":"404"}',
                    "gh: Not Found (HTTP 404)",
                ),
                "github-repository",
                "cannot resolve GitHub repository ned2/gone: Not Found (HTTP 404)",
            ),
            (
                CommandResult([], 1, "", "HTTP 401: Bad credentials"),
                "github-authentication",
                "cannot resolve GitHub repository ned2/gone: HTTP 401: Bad credentials",
            ),
        ]
        for result, code, message in cases:
            with self.subTest(code=code):
                runner = FixedRunner(result)
                with self.assertRaises(RuntimeError) as caught:
                    observe_github_repository_identity(
                        Path("/repo"), "ned2/gone", 7, runner
                    )
                self.assertEqual(code, getattr(caught.exception, "code", None))
                self.assertEqual(message, str(caught.exception))


class FixedRunner:
    def __init__(self, result: CommandResult) -> None:
        self.result = result

    def __call__(self, args, cwd, timeout) -> CommandResult:
        return self.result


class ProjectCollectorTests(unittest.TestCase):
    def test_combines_issue_and_target_observations(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: target_inventory(),
        )

        snapshot = collector.refresh()

        self.assertEqual("Build observer", snapshot.issues[0].title)
        self.assertEqual("project:example", snapshot.project_id)
        self.assertEqual("Example", snapshot.display_label)
        self.assertEqual("/repo", snapshot.observation_targets[0].path)
        self.assertEqual({}, snapshot.label_colors)

    def test_branches_travel_with_the_targets_half_of_the_snapshot(self) -> None:
        branch = Branch(
            refname="refs/heads/main",
            name="main",
            remote=None,
            head="abc123",
            committed_at="2026-08-27T00:00:00Z",
            unintegrated_commits=0,
        )
        anchors_seen: list[list[Path]] = []

        def observe_branches(anchors: Sequence[Path]) -> BranchObservation:
            anchors_seen.append(list(anchors))
            return BranchObservation(
                [branch],
                "2026-08-27T01:00:00Z",
                [],
                "refs/remotes/origin/main",
            )

        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: target_inventory(),
            branch_observer=observe_branches,
        )

        snapshot = collector.refresh()
        inventory = collector.observe_targets()

        self.assertEqual([[Path("/repo")], [Path("/repo")]], anchors_seen)
        self.assertEqual((branch,), snapshot.branches)
        self.assertEqual("2026-08-27T01:00:00Z", snapshot.fetched_at)
        self.assertEqual("refs/remotes/origin/main", snapshot.integration_ref)
        self.assertEqual((branch,), inventory.branches)
        self.assertEqual("2026-08-27T01:00:00Z", inventory.fetched_at)
        self.assertEqual("refs/remotes/origin/main", inventory.integration_ref)
        payload = jsonable(snapshot)
        self.assertEqual("refs/heads/main", payload["branches"][0]["refname"])
        self.assertEqual(0, payload["branches"][0]["unintegratedCommits"])
        self.assertEqual("2026-08-27T01:00:00Z", payload["fetchedAt"])
        self.assertEqual("refs/remotes/origin/main", payload["integrationRef"])

    def test_source_label_palette_travels_with_the_snapshot(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            PaletteSource(),
            target_observer=lambda _anchors: target_inventory(),
        )

        snapshot = collector.refresh()

        self.assertEqual({"enhancement": "a2eeef"}, snapshot.label_colors)
        self.assertEqual({"enhancement": "a2eeef"}, jsonable(snapshot)["labelColors"])
        activity = jsonable(snapshot)["issueActivity"][issue().id]
        self.assertEqual(2, activity["commentCount"])
        self.assertEqual(
            [{"number": 41, "url": "https://example.test/pull/41", "state": "merged"}],
            activity["linkedPullRequests"],
        )

    def test_empty_issue_project_retains_identity_and_display_label(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            EmptySource(),
            target_observer=lambda _anchors: target_inventory(),
        )

        snapshot = collector.refresh()
        payload = jsonable(snapshot)

        self.assertEqual((), snapshot.issues)
        self.assertEqual("project:example", payload["projectId"])
        self.assertEqual("Example", payload["displayLabel"])
        self.assertEqual("repository:example", payload["repositoryId"])

    def test_headless_issue_json_preserves_required_null_fields(self) -> None:
        payload = issue_payload()
        payload.update(
            {
                "stateReason": None,
                "author": None,
                "issueType": None,
                "milestone": None,
                "closedAt": None,
            }
        )
        payload["relationships"]["parent"] = None
        complete = conform_issue(payload)
        snapshot = project_snapshot(issues=[complete])

        serialized = jsonable(snapshot)["issues"][0]

        self.assertEqual(complete, conform_issue(serialized))
        self.assertEqual(complete.number, serialized["number"])
        self.assertIsNone(serialized["stateReason"])
        self.assertIsNone(serialized["relationships"]["parent"])
        self.assertIsNone(serialized["issueType"])
        self.assertIsNone(serialized["milestone"])

    def test_observes_all_anchors_but_refreshes_issues_once(self) -> None:
        source = CountingSource()
        project = ResolvedProject(
            "project:example",
            "Example",
            "repository:example",
            ("personal",),
            ("/clone-one", "/clone-two"),
            "/clone-one",
        )
        target = ObservationTarget(
            path="/clone-two-linked",
            head="def456",
            branch="feature",
            detached=False,
            dirty=True,
            availability="available",
            elapsed_ms=7,
            diagnostics=[],
            role="linked",
        )
        observed_anchors: list[Path] = []

        def observe_targets(anchors):
            observed_anchors.extend(anchors)
            return RepositoryStateInventory(targets=[target], diagnostics=[])

        collector = ProjectCollector(
            project,
            source,
            target_observer=observe_targets,
        )

        snapshot = collector.refresh()

        self.assertEqual([Path("/clone-one"), Path("/clone-two")], observed_anchors)
        self.assertEqual((target,), snapshot.observation_targets)
        self.assertEqual(1, len(snapshot.issues))
        self.assertEqual(1, source.collection_count)
        self.assertEqual(
            "/clone-two-linked",
            jsonable(snapshot)["observationTargets"][0]["path"],
        )

    def test_unavailable_target_does_not_degrade_issue_source(self) -> None:
        target = observation_target(
            availability="unavailable",
            dirty=None,
            diagnostics=[
                Diagnostic(
                    source="target:/repo",
                    severity="warning",
                    message="target unavailable",
                    code="target-inaccessible",
                )
            ],
        )
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: RepositoryStateInventory(
                targets=[target], diagnostics=[]
            ),
        )

        snapshot = collector.refresh()

        self.assertEqual("fresh", snapshot.issue_source_status)
        self.assertEqual(1, len(snapshot.issues))
        self.assertEqual("unavailable", snapshot.observation_targets[0].availability)

    def test_target_observer_failure_preserves_fresh_issues(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: (_ for _ in ()).throw(
                RuntimeError("target discovery crashed")
            ),
        )

        snapshot = collector.refresh()

        self.assertEqual("fresh", snapshot.issue_source_status)
        self.assertEqual(1, len(snapshot.issues))
        self.assertEqual((), snapshot.observation_targets)
        self.assertIn(
            "target-discovery", [diagnostic.code for diagnostic in snapshot.diagnostics]
        )

    def test_refresh_stamps_timestamps_from_the_injected_clock(self) -> None:
        ticks = iter(
            [
                "2026-09-02T00:00:01Z",
                "2026-09-02T00:00:02Z",
                "2026-09-02T00:00:03Z",
            ]
        )
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: target_inventory(),
            clock=lambda: next(ticks),
        )

        snapshot = collector.refresh()

        self.assertEqual("2026-09-02T00:00:01Z", snapshot.pull_request_attempted_at)
        self.assertEqual("2026-09-02T00:00:02Z", snapshot.target_attempted_at)
        self.assertEqual("2026-09-02T00:00:02Z", snapshot.target_last_good_at)
        self.assertEqual("2026-09-02T00:00:03Z", snapshot.collected_at)

    def test_refresh_target_failure_leaves_no_last_good_timestamp(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: (_ for _ in ()).throw(
                RuntimeError("target discovery crashed")
            ),
            clock=lambda: "2026-09-02T00:00:03Z",
        )

        snapshot = collector.refresh()

        self.assertEqual("unavailable", snapshot.target_status)
        self.assertEqual("2026-09-02T00:00:03Z", snapshot.target_attempted_at)
        self.assertIsNone(snapshot.target_last_good_at)
        self.assertEqual("2026-09-02T00:00:03Z", snapshot.collected_at)


class FakeProjectCollector:
    """Serve one prepared snapshot as independently observed Project parts."""

    def __init__(self, snapshot: ProjectSnapshot) -> None:
        self.snapshot = snapshot

    def observe_issues(self, *, reconcile: bool = False) -> IssueSourceObservation:
        return IssueSourceObservation(
            status=self.snapshot.issue_source_status,
            attempted_at=self.snapshot.issue_source_attempted_at,
            last_good_at=self.snapshot.issue_source_last_good_at,
            issues=tuple(self.snapshot.issues),
            diagnostics=(),
        )

    def observe_targets(self) -> RepositoryStateInventory:
        return RepositoryStateInventory(
            targets=copy.deepcopy(self.snapshot.observation_targets), diagnostics=[]
        )

    def observe_pull_requests(self) -> PullRequestSourceObservation:
        return PullRequestSourceObservation(
            status=self.snapshot.pull_request_status,
            attempted_at=(
                self.snapshot.pull_request_attempted_at
                or self.snapshot.issue_source_attempted_at
            ),
            last_good_at=self.snapshot.pull_request_last_good_at,
            pull_requests=tuple(self.snapshot.pull_requests),
            diagnostics=(),
        )


class ObservationCoordinatorTests(unittest.TestCase):
    """Coordinator behavior over real (if empty) anchor directories."""

    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    @override
    def tearDown(self) -> None:
        self.temporary.cleanup()

    def anchor(self, name: str) -> str:
        """A real directory for an anchor, so no ``is_dir`` needs patching."""
        path = self.root / name
        path.mkdir(exist_ok=True)
        return str(path)

    def test_workspace_correlates_run_to_transferred_issue_by_identity(self) -> None:
        project_a = resolved_project(self.anchor("project-a"), "project-a")
        project_b = resolved_project(self.anchor("project-b"), "project-b")
        snapshot_a = project_snapshot(
            self.anchor("project-a"), [], project_id="project-a"
        )
        transferred_payload = issue_payload("new/repository#70")
        transferred_payload["id"] = "I_stable"
        transferred_payload["projectId"] = "project-b"
        transferred = conform_issue(transferred_payload)
        snapshot_b = project_snapshot(
            self.anchor("project-b"), [transferred], project_id="project-b"
        )
        run = AgentRun(
            id="codex-session:transfer",
            harness="codex",
            process_or_session="transfer hook",
            state="running",
            observation_target=self.anchor("project-a"),
            observation_project_id="project-a",
            branch="issue/old/repository#7",
            issue_id="I_stable",
            issue_reference_hint="old/repository#7",
        )

        def factory(project, **_kwargs):
            snapshot = snapshot_a if project.project_id == "project-a" else snapshot_b
            return FakeProjectCollector(snapshot)

        collector = ObservationCoordinator(
            [project_a, project_b],
            factory=factory,
            agent_observer=lambda _targets: ([run], []),
        )

        snapshot = collector.refresh()

        self.assertEqual((run,), snapshot.agent_runs)
        self.assertEqual({"I_stable": (run.id,)}, snapshot.issue_runs)

    def test_unbound_hinted_run_stays_unbound_without_promotion(self) -> None:
        current_project = resolved_project(self.anchor("project-a"), "project-a")
        current_payload = issue_payload("owner/repository#15")
        current_payload["id"] = "I_observed"
        current_payload["projectId"] = "project-a"
        current_issue = conform_issue(current_payload)
        current_snapshot = project_snapshot(
            self.anchor("project-a"), [current_issue], project_id="project-a"
        )
        hinted_run = AgentRun(
            id="codex-session:hinted",
            harness="codex",
            process_or_session="hinted hook",
            state="running",
            observation_target=self.anchor("project-a"),
            observation_project_id="project-a",
            branch="main",
            issue_id=None,
            issue_reference_hint=None,
        )

        collector = ObservationCoordinator(
            [current_project],
            factory=lambda _project, **_kwargs: FakeProjectCollector(current_snapshot),
            agent_observer=lambda _targets: ([hinted_run], []),
        )

        snapshot = collector.refresh()

        self.assertEqual({"I_observed": ()}, snapshot.issue_runs)
        self.assertIsNone(snapshot.agent_runs[0].issue_id)
        self.assertEqual((), snapshot.diagnostics)

    def test_grouped_clone_target_collects_project_once(self) -> None:
        clone_one = self.anchor("clone-one")
        grouped = ResolvedProject(
            "project:example",
            "Example",
            "repository:example",
            ("personal",),
            (clone_one, self.anchor("clone-two")),
            clone_one,
        )
        factory_calls: list[ResolvedProject] = []

        def factory(current_target, **_kwargs):
            factory_calls.append(current_target)
            return FakeProjectCollector(project_snapshot(clone_one))

        collector = ObservationCoordinator(
            [grouped],
            factory=factory,
            agent_observer=lambda _targets: ([], []),
        )

        snapshot = collector.refresh()

        self.assertEqual([grouped], factory_calls)
        self.assertEqual(1, len(snapshot.projects))

    def test_one_failed_project_does_not_blank_the_workspace(self) -> None:
        good = self.anchor("good")
        bad = self.anchor("bad")
        good_snapshot = project_snapshot(good)

        def factory(current_target, **_kwargs):
            if current_target.primary_anchor == bad:
                raise RuntimeError("fixture failure")
            return FakeProjectCollector(good_snapshot)

        collector = ObservationCoordinator(
            [
                resolved_project(good, "project:good"),
                resolved_project(bad, "project:bad"),
            ],
            factory=factory,
            agent_observer=lambda _targets: ([], []),
        )

        snapshot = collector.refresh()

        self.assertEqual(
            ["fresh", "unavailable"],
            [project.status for project in snapshot.projects],
        )
        self.assertIn("fixture failure", snapshot.projects[1].diagnostics[0].message)

    def test_agent_observer_failure_does_not_blank_projects(self) -> None:
        repo = self.anchor("repo")
        collector = ObservationCoordinator(
            [resolved_project(repo)],
            factory=lambda _project, **_kwargs: FakeProjectCollector(
                project_snapshot(repo)
            ),
            agent_observer=lambda _targets: (_ for _ in ()).throw(
                RuntimeError("agent observation crashed")
            ),
        )

        snapshot = collector.refresh()

        self.assertEqual(1, len(snapshot.projects))
        self.assertIsNotNone(snapshot.projects[0].snapshot)
        self.assertEqual((), snapshot.agent_runs)
        self.assertEqual("agent-observation", snapshot.diagnostics[0].code)

    def test_overlapping_refreshes_are_serialized(self) -> None:
        repo = self.anchor("repo")
        active = 0
        maximum_active = 0
        counter_lock = threading.Lock()
        # The barrier holds the first observation open long enough for an
        # unserialized second refresh to enter it, which the overlap counter
        # would record. Serialized refreshes never meet: the first times out
        # at the barrier and proceeds alone, and each caller still gets a
        # complete workspace — an unserialized run is superseded mid-flight
        # and hands one caller a workspace with no projects.
        overlap_window = threading.Barrier(2)
        good_snapshot = project_snapshot(repo)

        class GatedCollector(FakeProjectCollector):
            @override
            def observe_issues(
                self, *, reconcile: bool = False
            ) -> IssueSourceObservation:
                nonlocal active, maximum_active
                with counter_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                with contextlib.suppress(threading.BrokenBarrierError):
                    overlap_window.wait(timeout=0.25)
                with counter_lock:
                    active -= 1
                return super().observe_issues()

        collector = ObservationCoordinator(
            [resolved_project(repo)],
            factory=lambda _target, **_kwargs: GatedCollector(good_snapshot),
            agent_observer=lambda _targets: ([], []),
        )
        results: list[WorkspaceSnapshot] = []

        def refresh() -> None:
            results.append(collector.refresh())

        first = threading.Thread(target=refresh)
        second = threading.Thread(target=refresh)
        first.start()
        second.start()
        first.join()
        second.join()

        self.assertEqual(1, maximum_active)
        self.assertEqual(2, len(results))
        for workspace in results:
            self.assertEqual(1, len(workspace.projects))
            self.assertEqual("fresh", workspace.projects[0].status)
