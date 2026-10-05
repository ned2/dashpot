from __future__ import annotations

import contextlib
import copy
import json
import tempfile
import threading
import unittest
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, override

from app_harness import NOW, PROJECT_ID, SnapshotQuerySource, workspace_snapshot
from app_harness import issue as harness_issue
from dashpot.core.commands import CommandResult
from dashpot.core.issue_profile import IssueProfile, conform_issue
from dashpot.core.model import (
    AgentRun,
    Branch,
    Diagnostic,
    IssueActivity,
    LinkedPullRequest,
    ObservationTarget,
    ProjectSnapshot,
    RepositoryStateInventory,
    WorkspaceSnapshot,
)
from dashpot.github.github_repository import (
    RepositoryIdentityError,
    observe_github_repository_identity,
)
from dashpot.issues.issue_sources import IssueSourceObservation
from dashpot.issues.pull_request_sources import PullRequestSourceObservation
from dashpot.observation.collect import (
    ObservationCoordinator,
    ProjectCollector,
    create_project_collector,
)
from dashpot.project.workspace import ResolvedProject
from dashpot.queries.markdown_queries import MarkdownQuerySource
from dashpot.queries.source_queries import (
    AuxiliaryObservation,
    QuerySource,
    ResourceKind,
    SourceEnumeration,
)
from dashpot.repository.repository import BranchObservation
from factories import dashpot_project, observation_target
from helpers import jsonable, snapshot_of

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

    def test_an_answer_missing_its_identity_or_name_is_refused(self) -> None:
        cases = [
            ({"full_name": "ned2/dashpot"}, "no durable identity"),
            ({"node_id": "R_dashpot", "full_name": ""}, "no full name"),
        ]
        for payload, reason in cases:
            with self.subTest(reason=reason):
                runner = FixedRunner(CommandResult([], 0, json.dumps(payload), ""))
                with self.assertRaisesRegex(RepositoryIdentityError, reason):
                    observe_github_repository_identity(
                        Path("/repo"), "ned2/dashpot", 7, runner
                    )


class FixedRunner:
    def __init__(self, result: CommandResult) -> None:
        self.result = result

    def __call__(self, args, cwd, timeout) -> CommandResult:
        return self.result


class EnumeratingSource(SnapshotQuerySource):
    """Enumerate a snapshot's Project, with the auxiliary facts a provider reports."""

    def __init__(
        self,
        snapshot: WorkspaceSnapshot,
        auxiliary: Mapping[str, AuxiliaryObservation] | None = None,
    ) -> None:
        super().__init__(snapshot)
        self.auxiliary = dict(auxiliary or {})
        self.enumerations: list[ResourceKind] = []

    @override
    def enumerate_source(self, kind: ResourceKind) -> SourceEnumeration:
        self.enumerations.append(kind)
        enumeration = super().enumerate_source(kind)
        if kind != "issues":
            return enumeration
        return enumeration.model_copy(update={"auxiliary": self.auxiliary})


def no_branches(_anchors: Sequence[Path]) -> BranchObservation:
    return BranchObservation([], None, [])


def exported(
    tmp_path: Path,
    source: QuerySource,
    *,
    anchors: Sequence[str] = ("repo",),
    target_observer: Callable[[Sequence[Path]], RepositoryStateInventory] = (
        lambda _anchors: target_inventory()
    ),
    branch_observer: Callable[[Sequence[Path]], BranchObservation] = no_branches,
    clock: Callable[[], str] = lambda: NOW,
) -> ProjectSnapshot:
    """The one Project a headless export observes through ``source``."""
    paths = [tmp_path / anchor for anchor in anchors]
    for path in paths:
        path.mkdir(exist_ok=True)
    project = ResolvedProject(
        PROJECT_ID,
        "Test Repository",
        "repository:test-repo",
        ("test",),
        tuple(str(path) for path in paths),
        str(paths[0]),
    )
    coordinator = ObservationCoordinator(
        [project],
        factory=lambda project, **_kwargs: ProjectCollector(
            project,
            source,
            target_observer=target_observer,
            branch_observer=branch_observer,
        ),
        agent_observer=lambda _targets: ([], []),
        clock=clock,
    )
    return snapshot_of(coordinator.refresh().projects[0])


def test_combines_issue_and_target_observations(tmp_path: Path) -> None:
    source = EnumeratingSource(
        workspace_snapshot(harness_issue("test/repo#7", "Build"))
    )

    snapshot = exported(tmp_path, source)

    assert snapshot.issues[0].title == "Build"
    assert snapshot.project_id == PROJECT_ID
    assert snapshot.display_label == "Test Repository"
    assert snapshot.observation_targets[0].path == "/repo"
    assert snapshot.label_colors == {}
    assert source.enumerations.count("issues") == 1
    assert source.enumerations.count("pull-requests") == 1


def test_branches_travel_with_the_targets_half_of_the_snapshot(
    tmp_path: Path,
) -> None:
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

    snapshot = exported(
        tmp_path,
        EnumeratingSource(workspace_snapshot()),
        branch_observer=observe_branches,
    )

    assert anchors_seen == [[tmp_path / "repo"]]
    assert snapshot.branches == (branch,)
    assert snapshot.fetched_at == "2026-08-27T01:00:00Z"
    assert snapshot.integration_ref == "refs/remotes/origin/main"
    payload = jsonable(snapshot)
    assert payload["branches"][0]["refname"] == "refs/heads/main"
    assert payload["branches"][0]["unintegratedCommits"] == 0
    assert payload["fetchedAt"] == "2026-08-27T01:00:00Z"
    assert payload["integrationRef"] == "refs/remotes/origin/main"


def test_source_label_palette_and_activity_travel_with_the_snapshot(
    tmp_path: Path,
) -> None:
    listed = harness_issue("test/repo#7", "Build")
    activity = IssueActivity(
        comment_count=2,
        linked_pull_requests=[
            LinkedPullRequest(
                number=41, url="https://example.test/pull/41", state="merged"
            )
        ],
    )
    source = EnumeratingSource(
        workspace_snapshot(listed),
        {
            listed.id: AuxiliaryObservation(
                status="fresh",
                attempted_at=NOW,
                last_good_at=NOW,
                activity=activity,
                label_colors={"enhancement": "a2eeef"},
            )
        },
    )

    snapshot = exported(tmp_path, source)

    assert snapshot.label_colors == {"enhancement": "a2eeef"}
    assert jsonable(snapshot)["labelColors"] == {"enhancement": "a2eeef"}
    observed = jsonable(snapshot)["issueActivity"][listed.id]
    assert observed["commentCount"] == 2
    assert observed["linkedPullRequests"] == [
        {"number": 41, "url": "https://example.test/pull/41", "state": "merged"}
    ]


def test_empty_issue_project_retains_identity_and_display_label(
    tmp_path: Path,
) -> None:
    snapshot = exported(tmp_path, EnumeratingSource(workspace_snapshot()))
    payload = jsonable(snapshot)

    assert snapshot.issues == ()
    assert payload["projectId"] == PROJECT_ID
    assert payload["displayLabel"] == "Test Repository"
    assert payload["repositoryId"] == "repository:test-repo"


def test_headless_issue_json_preserves_required_null_fields() -> None:
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

    assert conform_issue(serialized) == complete
    assert serialized["number"] == complete.number
    assert serialized["stateReason"] is None
    assert serialized["relationships"]["parent"] is None
    assert serialized["issueType"] is None
    assert serialized["milestone"] is None


def test_observes_all_anchors_but_enumerates_issues_once(tmp_path: Path) -> None:
    source = EnumeratingSource(
        workspace_snapshot(harness_issue("test/repo#7", "Build"))
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

    def observe_targets(anchors: Sequence[Path]) -> RepositoryStateInventory:
        observed_anchors.extend(anchors)
        return RepositoryStateInventory(targets=[target], diagnostics=[])

    snapshot = exported(
        tmp_path,
        source,
        anchors=("clone-one", "clone-two"),
        target_observer=observe_targets,
    )

    assert observed_anchors == [tmp_path / "clone-one", tmp_path / "clone-two"]
    assert snapshot.observation_targets == (target,)
    assert len(snapshot.issues) == 1
    assert source.enumerations.count("issues") == 1
    assert jsonable(snapshot)["observationTargets"][0]["path"] == "/clone-two-linked"


def test_unavailable_target_does_not_degrade_issue_source(tmp_path: Path) -> None:
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

    snapshot = exported(
        tmp_path,
        EnumeratingSource(workspace_snapshot(harness_issue("test/repo#7", "Build"))),
        target_observer=lambda _anchors: RepositoryStateInventory(
            targets=[target], diagnostics=[]
        ),
    )

    assert snapshot.issue_source_status == "fresh"
    assert len(snapshot.issues) == 1
    assert snapshot.observation_targets[0].availability == "unavailable"


def test_target_observer_failure_preserves_fresh_issues(tmp_path: Path) -> None:
    def crash(_anchors: Sequence[Path]) -> RepositoryStateInventory:
        raise RuntimeError("target discovery crashed")

    snapshot = exported(
        tmp_path,
        EnumeratingSource(workspace_snapshot(harness_issue("test/repo#7", "Build"))),
        target_observer=crash,
        clock=lambda: "2026-09-02T00:00:03Z",
    )

    assert snapshot.issue_source_status == "fresh"
    assert len(snapshot.issues) == 1
    assert snapshot.observation_targets == ()
    assert snapshot.target_status == "unavailable"
    assert snapshot.target_attempted_at == "2026-09-02T00:00:03Z"
    assert snapshot.target_last_good_at is None
    assert "target discovery crashed" in " ".join(
        diagnostic.message for diagnostic in snapshot.diagnostics
    )


def test_the_export_stamps_its_observations_from_the_coordinators_clock(
    tmp_path: Path,
) -> None:
    snapshot = exported(
        tmp_path,
        EnumeratingSource(workspace_snapshot()),
        clock=lambda: "2026-09-02T00:00:02Z",
    )

    assert snapshot.target_attempted_at == "2026-09-02T00:00:02Z"
    assert snapshot.target_last_good_at == "2026-09-02T00:00:02Z"
    assert snapshot.collected_at == "2026-09-02T00:00:02Z"


def test_the_export_observes_a_configured_project_through_its_query_source(
    tmp_path: Path,
) -> None:
    root = dashpot_project(tmp_path / "repo").resolve()
    project = ResolvedProject(
        "project:test", "Test", "repository:test", ("test",), (str(root),), str(root)
    )
    built: list[ProjectCollector] = []

    def factory(project: ResolvedProject, **kwargs: Any) -> ProjectCollector:
        collector = create_project_collector(project, **kwargs)
        built.append(collector)
        return collector

    coordinator = ObservationCoordinator(
        [project], factory=factory, agent_observer=lambda _targets: ([], [])
    )

    snapshot = snapshot_of(coordinator.refresh().projects[0])

    assert [type(collector.query_source) for collector in built] == [
        MarkdownQuerySource
    ]
    assert sorted(issue.title for issue in snapshot.issues) == [
        "Build observer",
        "Fix crash",
    ]
    assert snapshot.issue_source_status == "fresh"
    # A Markdown Project has no Pull Requests to enumerate.
    assert snapshot.pull_request_status == "unavailable"
    assert [target.path for target in snapshot.observation_targets] == [str(root)]


def test_the_export_builds_each_projects_collector_once(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("alpha", "beta")]
    for root in roots:
        root.mkdir()
    projects = [resolved_project(str(root), f"project:{root.name}") for root in roots]
    # Every half of every Project asks for its collector at once; each
    # build waits until all of them have asked, so a coordinator that built
    # per half would build each collector three times. A coordinator that
    # builds once holds the other halves on its lock, short of the barrier,
    # so on correct code the barrier breaks after its timeout: no observable
    # point marks a half waiting on that lock to release it sooner.
    arrived = threading.Barrier(len(projects) * 3, timeout=0.5)
    builds: list[str] = []
    lock = threading.Lock()

    def factory(project: ResolvedProject, **_kwargs: Any) -> FakeProjectCollector:
        with lock:
            builds.append(project.project_id)
        with contextlib.suppress(threading.BrokenBarrierError):
            arrived.wait()
        return FakeProjectCollector(
            project_snapshot(project.primary_anchor, project_id=project.project_id)
        )

    coordinator = ObservationCoordinator(
        projects, factory=factory, agent_observer=lambda _targets: ([], [])
    )

    snapshot = coordinator.refresh()

    assert sorted(builds) == ["project:alpha", "project:beta"]
    assert [project.status for project in snapshot.projects] == ["fresh", "fresh"]


class FakeProjectCollector:
    """Serve one prepared snapshot as independently observed Project parts."""

    def __init__(self, snapshot: ProjectSnapshot) -> None:
        self.snapshot = snapshot

    def observe_issues(self) -> IssueSourceObservation:
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
            def observe_issues(self) -> IssueSourceObservation:
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


def test_enumeration_keeps_fallback_diagnostic_codes_for_both_source_families():
    from unittest.mock import Mock

    from dashpot.queries.source_queries import (
        QuerySource,
        SourceContext,
        SourceEnumeration,
    )

    context = SourceContext(
        project_id="project:example",
        repository_id="repository:example",
        source="github",
        location="github.com",
    )
    diagnostics = (
        Diagnostic(source="github", severity="warning", message="missing code"),
        Diagnostic(source="github", severity="warning", message="empty code", code=""),
        Diagnostic(
            source="github", severity="warning", message="coded", code="github-network"
        ),
    )
    query = Mock(spec=QuerySource)
    query.enumerate_source.side_effect = lambda kind: SourceEnumeration(
        context=context,
        kind=kind,
        status="unavailable",
        attempted_at="2026-09-17T00:00:00Z",
        last_good_at=None,
        diagnostics=diagnostics,
    )
    collector = ProjectCollector(resolved_project(), query)
    for observation in (collector.observe_issues(), collector.observe_pull_requests()):
        assert [d.code for d in observation.diagnostics] == [
            "source-unavailable",
            "source-unavailable",
            "github-network",
        ]
        assert observation.diagnostics[2] is diagnostics[2]
    assert diagnostics[0].code is None
    assert diagnostics[1].code == ""
