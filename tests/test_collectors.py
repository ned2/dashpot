from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from dashpot.agents import (
    HookRecordStore,
    ProcessIdentity,
    nearest_codex_process,
    observe_hook_runs,
    process_info,
    publish_hook_event,
    write_hook_record,
)
from dashpot.agent_bindings import IssueBindingPromotion
from dashpot.collect import ProjectCollector, WorkspaceCollector
from dashpot.commands import CommandResult
from dashpot.issue_sources import IssueSource
from dashpot.issue_profile import conform_issue
from dashpot.model import (
    AgentRun,
    Diagnostic,
    ObservationTarget,
    ObservationTargetInventory,
    ProjectSnapshot,
    ResolvedProject,
    to_jsonable,
)
from dashpot.repository import observe_github_repository_identity


ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def observation_target(root: str = "/repo") -> ObservationTarget:
    return ObservationTarget(
        root,
        "abc123",
        "main",
        False,
        False,
        "available",
        2,
        [],
    )


def target_inventory(root: str = "/repo") -> ObservationTargetInventory:
    return ObservationTargetInventory([observation_target(root)], [])


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
    root: str = "/repo", issues: list[dict] | None = None
) -> ProjectSnapshot:
    return ProjectSnapshot(
        project_id="project:example",
        display_label="Example",
        repository_id="repository:example",
        collected_at="2026-08-24T15:00:00Z",
        issue_source_status="fresh",
        issue_source_attempted_at="2026-08-24T15:00:00Z",
        issue_source_last_good_at="2026-08-24T15:00:00Z",
        observation_targets=[observation_target(root)],
        issues=[issue()] if issues is None else issues,
        diagnostics=[],
    )


def issue(reference: str = "example/project#7") -> dict:
    value = copy.deepcopy(ISSUE_FIXTURE)
    value["reference"] = reference
    value["id"] = f"I_{reference}"
    value["title"] = "Build observer"
    return value


class FakeSource(IssueSource):
    @property
    def name(self) -> str:
        return "fake"

    def _collect(self) -> list[dict]:
        return [issue()]


class EmptySource(IssueSource):
    @property
    def name(self) -> str:
        return "empty"

    def _collect(self) -> list[dict]:
        return []


class CountingSource(FakeSource):
    def __init__(self) -> None:
        super().__init__()
        self.collection_count = 0

    def _collect(self) -> list[dict]:
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
                json.dumps(
                    {"node_id": "R_dashpot", "full_name": "ned2/dashpot"}
                ),
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


class ProjectCollectorTests(unittest.TestCase):
    def test_combines_issue_and_target_observations(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: target_inventory(),
        )

        snapshot = collector.refresh()

        self.assertEqual("Build observer", snapshot.issues[0]["title"])
        self.assertEqual("project:example", snapshot.project_id)
        self.assertEqual("Example", snapshot.display_label)
        self.assertEqual("/repo", snapshot.observation_targets[0].path)

    def test_empty_issue_project_retains_identity_and_display_label(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            EmptySource(),
            target_observer=lambda _anchors: target_inventory(),
        )

        snapshot = collector.refresh()
        payload = to_jsonable(snapshot)

        self.assertEqual([], snapshot.issues)
        self.assertEqual("project:example", payload["projectId"])
        self.assertEqual("Example", payload["displayLabel"])
        self.assertEqual("repository:example", payload["repositoryId"])

    def test_headless_issue_json_preserves_required_null_fields(self) -> None:
        complete = issue()
        complete.update(
            {
                "stateReason": None,
                "author": None,
                "issueType": None,
                "milestone": None,
                "closedAt": None,
            }
        )
        complete["relationships"]["parent"] = None
        snapshot = project_snapshot(issues=[complete])

        serialized = to_jsonable(snapshot)["issues"][0]

        self.assertEqual(complete, conform_issue(serialized))
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
            "/clone-two-linked",
            "def456",
            "feature",
            False,
            True,
            "available",
            7,
            [],
        )
        observed_anchors: list[Path] = []

        def observe_targets(anchors):
            observed_anchors.extend(anchors)
            return ObservationTargetInventory([target], [])

        collector = ProjectCollector(
            project,
            source,
            target_observer=observe_targets,
        )

        snapshot = collector.refresh()

        self.assertEqual([Path("/clone-one"), Path("/clone-two")], observed_anchors)
        self.assertEqual([target], snapshot.observation_targets)
        self.assertEqual(1, len(snapshot.issues))
        self.assertEqual(1, source.collection_count)
        self.assertEqual(
            "/clone-two-linked",
            to_jsonable(snapshot)["observationTargets"][0]["path"],
        )

    def test_unavailable_target_does_not_degrade_issue_source(self) -> None:
        target = observation_target()
        target.availability = "unavailable"
        target.dirty = None
        target.diagnostics.append(
            Diagnostic(
                "target:/repo",
                "warning",
                "target unavailable",
                "target-inaccessible",
            )
        )
        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: ObservationTargetInventory(
                [target], []
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
        self.assertEqual([], snapshot.observation_targets)
        self.assertEqual("target-discovery", snapshot.diagnostics[0].code)


class HookObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(
        self,
        session_id: str,
        state: str,
        process: ProcessIdentity | None = None,
        *,
        cwd: str = "/repo",
        repository_root: str = "/repo",
    ) -> None:
        write_hook_record(
            {
                "version": 2,
                "sessionId": session_id,
                "harness": "codex",
                "state": state,
                "cwd": cwd,
                "repositoryRoot": repository_root,
                "branch": "main",
                "issueReferenceHint": "example/project#7",
                "event": "Stop" if state == "waiting" else "PreToolUse",
                "lastActivityAt": "2026-08-24T15:00:00Z",
                "sessionProcess": process.as_record() if process else None,
            },
            self.state_dir,
        )

    def test_live_record_is_returned(self) -> None:
        self.write("live", "waiting", self.process)

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual("waiting", runs[0].state)
        self.assertEqual("example/project#7", runs[0].issue_reference_hint)
        self.assertEqual([], diagnostics)

    def test_linked_worktree_record_is_associated_with_its_target(self) -> None:
        linked = observation_target("/repo-linked")
        linked.branch = "feature"
        self.write(
            "linked",
            "running",
            self.process,
            cwd="/repo-linked/src",
            repository_root="/repo-linked",
        )

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target(), linked]},
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("/repo-linked", runs[0].observation_target)

    def test_recorded_root_and_cwd_must_resolve_to_the_same_target(self) -> None:
        self.write(
            "mismatch",
            "running",
            self.process,
            cwd="/outside-project",
            repository_root="/repo",
        )

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], runs)
        self.assertEqual("agent-target-mismatch", diagnostics[0].code)

    def test_ended_and_orphaned_records_are_not_active(self) -> None:
        self.write("ended", "ended", self.process)
        self.write("orphaned", "running", self.process)

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=lambda _pid: None,
            isolated=False,
        )

        self.assertEqual([], runs)
        self.assertEqual(1, len(diagnostics))
        self.assertIn("orphaned", diagnostics[0].message)

    def test_hidden_host_process_degrades_to_unknown(self) -> None:
        self.write("sandboxed", "running", self.process)

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=lambda _pid: None,
            isolated=True,
        )

        self.assertEqual("unknown", runs[0].state)
        self.assertIn("liveness is unknown", diagnostics[0].message)

    def test_malformed_record_becomes_diagnostic(self) -> None:
        (self.state_dir / "bad.json").write_text(json.dumps({"version": 99}))

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]}, self.state_dir
        )

        self.assertEqual([], runs)
        self.assertIn("unsupported record", diagnostics[0].message)

    def test_whitespace_issue_identity_makes_record_invalid(self) -> None:
        self.write("invalid-identity", "waiting", self.process)
        path = self.state_dir / "invalid-identity.json"
        record = json.loads(path.read_text())
        record["issueId"] = "not an identity"
        path.write_text(json.dumps(record))

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]}, self.state_dir
        )

        self.assertEqual([], runs)
        self.assertIn("issueId must be a whitespace-free", diagnostics[0].message)

    def test_record_session_must_match_filename(self) -> None:
        self.write("actual-session", "waiting", self.process)
        (self.state_dir / "actual-session.json").rename(
            self.state_dir / "different-session.json"
        )

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]}, self.state_dir
        )

        self.assertEqual([], runs)
        self.assertIn("does not match its filename", diagnostics[0].message)

    def test_resume_event_preserves_initial_issue_binding(self) -> None:
        base_event = {
            "session_id": "resume-me",
            "cwd": "/repo",
            "hook_event_name": "SessionStart",
        }
        publish_hook_event(
            base_event,
            self.state_dir,
            environ={
                "DASHPOT_ISSUE_ID": "I_stable",
                "DASHPOT_ISSUE_REF": "example/project#7",
            },
            process=self.process,
        )

        publish_hook_event(
            {**base_event, "hook_event_name": "Stop"},
            self.state_dir,
            environ={},
            process=self.process,
        )

        record = json.loads((self.state_dir / "resume-me.json").read_text())
        self.assertEqual(2, record["version"])
        self.assertEqual("I_stable", record["issueId"])
        self.assertEqual("example/project#7", record["issueReferenceHint"])
        self.assertEqual("waiting", record["state"])

    def test_write_rejects_malformed_issue_values(self) -> None:
        record = {
            "version": 2,
            "sessionId": "invalid-write",
            "issueId": "not an identity",
            "issueReferenceHint": "example/project#7",
        }

        with self.assertRaisesRegex(RuntimeError, "whitespace-free"):
            write_hook_record(record, self.state_dir)

        self.assertFalse((self.state_dir / "invalid-write.json").exists())

    def test_reference_promotion_persists_identity_without_losing_lifecycle(
        self,
    ) -> None:
        event = {
            "session_id": "promote-me",
            "cwd": "/repo",
            "hook_event_name": "Stop",
        }
        publish_hook_event(
            event,
            self.state_dir,
            environ={"DASHPOT_ISSUE_REF": "example/project#7"},
            process=self.process,
        )
        observed = json.loads((self.state_dir / "promote-me.json").read_text())

        succeeded, diagnostic = HookRecordStore(self.state_dir).promote(
            IssueBindingPromotion(
                "codex-session:promote-me",
                "I_promoted",
                "reference",
                "example/project#7",
                "/repo",
                observed["lastActivityAt"],
            )
        )

        record = json.loads((self.state_dir / "promote-me.json").read_text())
        self.assertTrue(succeeded)
        self.assertIsNone(diagnostic)
        self.assertEqual("I_promoted", record["issueId"])
        self.assertEqual("waiting", record["state"])
        self.assertEqual("Stop", record["event"])

    def test_changed_hint_rejects_stale_promotion_without_losing_new_event(
        self,
    ) -> None:
        base = {"session_id": "racing", "cwd": "/repo"}
        publish_hook_event(
            {**base, "hook_event_name": "SessionStart"},
            self.state_dir,
            environ={"DASHPOT_ISSUE_REF": "example/project#7"},
            process=self.process,
        )
        observed = json.loads((self.state_dir / "racing.json").read_text())
        promotion = IssueBindingPromotion(
            "codex-session:racing",
            "I_old",
            "reference",
            "example/project#7",
            "/repo",
            observed["lastActivityAt"],
        )
        publish_hook_event(
            {**base, "hook_event_name": "Stop"},
            self.state_dir,
            environ={"DASHPOT_ISSUE_REF": "example/project#8"},
            process=self.process,
        )

        succeeded, diagnostic = HookRecordStore(self.state_dir).promote(
            promotion
        )

        record = json.loads((self.state_dir / "racing.json").read_text())
        self.assertFalse(succeeded)
        self.assertEqual("agent-issue-binding-race", diagnostic.code)
        self.assertIsNone(record["issueId"])
        self.assertEqual("example/project#8", record["issueReferenceHint"])
        self.assertEqual("waiting", record["state"])

    def test_concurrent_event_and_promotion_preserve_both_updates(self) -> None:
        base = {"session_id": "concurrent", "cwd": "/repo"}
        publish_hook_event(
            {**base, "hook_event_name": "SessionStart"},
            self.state_dir,
            environ={"DASHPOT_ISSUE_REF": "example/project#7"},
            process=self.process,
        )
        store = HookRecordStore(self.state_dir)
        observed = json.loads((self.state_dir / "concurrent.json").read_text())
        promotion = IssueBindingPromotion(
            "codex-session:concurrent",
            "I_concurrent",
            "reference",
            "example/project#7",
            "/repo",
            observed["lastActivityAt"],
        )
        barrier = threading.Barrier(3)
        failures: list[Exception] = []
        promotion_results: list[tuple[bool, Diagnostic | None]] = []

        def publish() -> None:
            barrier.wait()
            try:
                publish_hook_event(
                    {**base, "hook_event_name": "Stop"},
                    self.state_dir,
                    environ={},
                    process=self.process,
                )
            except Exception as exc:  # pragma: no cover - asserted below.
                failures.append(exc)

        def promote() -> None:
            barrier.wait()
            try:
                promotion_results.append(store.promote(promotion))
            except Exception as exc:  # pragma: no cover - asserted below.
                failures.append(exc)

        publisher = threading.Thread(target=publish)
        promoter = threading.Thread(target=promote)
        publisher.start()
        promoter.start()
        barrier.wait()
        publisher.join()
        promoter.join()

        record = json.loads((self.state_dir / "concurrent.json").read_text())
        self.assertEqual([], failures)
        self.assertEqual("waiting", record["state"])
        succeeded, diagnostic = promotion_results[0]
        if succeeded:
            self.assertIsNone(diagnostic)
            self.assertEqual("I_concurrent", record["issueId"])
        else:
            self.assertEqual("agent-issue-binding-race", diagnostic.code)
            self.assertIsNone(record["issueId"])

    def test_changed_target_rejects_stale_promotion(self) -> None:
        base = {"session_id": "moved", "cwd": "/repo"}
        publish_hook_event(
            {**base, "hook_event_name": "SessionStart"},
            self.state_dir,
            environ={"DASHPOT_ISSUE_REF": "example/project#7"},
            process=self.process,
        )
        path = self.state_dir / "moved.json"
        observed = json.loads(path.read_text())
        promotion = IssueBindingPromotion(
            "codex-session:moved",
            "I_old_project",
            "reference",
            "example/project#7",
            "/repo",
            observed["lastActivityAt"],
        )
        moved = {**observed, "cwd": "/other", "repositoryRoot": "/other"}
        HookRecordStore(self.state_dir).write(moved)

        succeeded, diagnostic = HookRecordStore(self.state_dir).promote(promotion)

        record = json.loads(path.read_text())
        self.assertFalse(succeeded)
        self.assertEqual("agent-issue-binding-race", diagnostic.code)
        self.assertIsNone(record["issueId"])

    def test_unsafe_promotion_run_id_is_rejected(self) -> None:
        succeeded, diagnostic = HookRecordStore(self.state_dir).promote(
            IssueBindingPromotion(
                "codex-session:../escape",
                "I_escape",
                "reference",
                "example/project#7",
                "/repo",
                "2026-08-27T00:00:00Z",
            )
        )

        self.assertFalse(succeeded)
        self.assertEqual("agent-issue-binding-conflict", diagnostic.code)
        self.assertFalse((self.state_dir.parent / "escape.json").exists())

    def test_nearest_codex_process_skips_sandbox_helper(self) -> None:
        sandbox = ProcessIdentity(
            10,
            20,
            "codex",
            "Tue Aug 25 01:00:00 2026",
            "codex-linux-sandbox --sandbox-policy-cwd /repo",
        )
        host = ProcessIdentity(
            20,
            1,
            "codex",
            "Tue Aug 25 00:59:00 2026",
            "/usr/bin/codex",
        )

        with mock.patch("dashpot.agents.os.getppid", return_value=10):
            result = nearest_codex_process(
                lookup=lambda pid: {10: sandbox, 20: host}.get(pid)
            )

        self.assertEqual(host, result)

    def test_process_info_parses_portable_ps_fields_and_arguments(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=(
                "42 1 codex Tue Aug 25 01:00:00 2026 "
                "/opt/codex exec --sandbox workspace-write\n"
            ),
        )

        with mock.patch("dashpot.agents.subprocess.run", return_value=completed) as run:
            result = process_info(42)

        self.assertEqual(
            ProcessIdentity(
                42,
                1,
                "codex",
                "Tue Aug 25 01:00:00 2026",
                "/opt/codex exec --sandbox workspace-write",
            ),
            result,
        )
        arguments = run.call_args.args[0]
        self.assertEqual(5, arguments.count("-o"))
        self.assertEqual("C", run.call_args.kwargs["env"]["LC_ALL"])


class FakeProjectCollector:
    def __init__(self, snapshot: ProjectSnapshot) -> None:
        self.snapshot = snapshot

    def refresh(self) -> ProjectSnapshot:
        return self.snapshot


class WorkspaceCollectorTests(unittest.TestCase):
    def test_workspace_correlates_run_to_transferred_issue_by_identity(self) -> None:
        project_a = resolved_project("/project-a", "project-a")
        project_b = resolved_project("/project-b", "project-b")
        snapshot_a = project_snapshot("/project-a", [])
        snapshot_a.project_id = "project-a"
        transferred = issue("new/repository#70")
        transferred["id"] = "I_stable"
        transferred["projectId"] = "project-b"
        snapshot_b = project_snapshot("/project-b", [transferred])
        snapshot_b.project_id = "project-b"
        run = AgentRun(
            id="codex-session:transfer",
            harness="codex",
            process_or_session="transfer hook",
            state="running",
            observation_target="/project-a",
            observation_project_id="project-a",
            branch="issue/old/repository#7",
            issue_id="I_stable",
            issue_reference_hint="old/repository#7",
        )

        def factory(project, **_kwargs):
            snapshot = snapshot_a if project.project_id == "project-a" else snapshot_b
            return FakeProjectCollector(snapshot)

        collector = WorkspaceCollector(
            [project_a, project_b],
            factory=factory,
            agent_observer=lambda _targets: ([run], []),
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual([run], snapshot.agent_runs)
        self.assertEqual({"I_stable": [run.id]}, snapshot.issue_runs)

    def test_workspace_claims_hint_relationship_only_after_promotion(self) -> None:
        current_project = resolved_project("/project-a", "project-a")
        current_issue = issue("owner/repository#15")
        current_issue["id"] = "I_promoted"
        current_issue["projectId"] = "project-a"
        current_snapshot = project_snapshot("/project-a", [current_issue])
        current_snapshot.project_id = "project-a"
        hinted_run = AgentRun(
            id="codex-session:hinted",
            harness="codex",
            process_or_session="hinted hook",
            state="running",
            observation_target="/project-a",
            observation_project_id="project-a",
            branch="main",
            issue_id=None,
            issue_reference_hint="owner/repository#15",
        )
        promotions: list[IssueBindingPromotion] = []

        def promote(binding):
            promotions.append(binding)
            return True, None

        collector = WorkspaceCollector(
            [current_project],
            factory=lambda _project, **_kwargs: FakeProjectCollector(
                current_snapshot
            ),
            agent_observer=lambda _targets: ([hinted_run], []),
            binding_promoter=promote,
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual(1, len(promotions))
        self.assertEqual({"I_promoted": [hinted_run.id]}, snapshot.issue_runs)
        self.assertEqual("I_promoted", snapshot.agent_runs[0].issue_id)
        self.assertIsNone(hinted_run.issue_id)
        payload = to_jsonable(snapshot)
        self.assertEqual("I_promoted", payload["agentRuns"][0]["issueId"])
        self.assertEqual(
            "project-a", payload["agentRuns"][0]["observationProjectId"]
        )
        self.assertEqual(
            [hinted_run.id], payload["issueRuns"]["I_promoted"]
        )

    def test_failed_promotion_leaves_hint_unbound_for_that_refresh(self) -> None:
        current_project = resolved_project("/project-a", "project-a")
        current_issue = issue("owner/repository#15")
        current_issue["id"] = "I_not_persisted"
        current_issue["projectId"] = "project-a"
        current_snapshot = project_snapshot("/project-a", [current_issue])
        current_snapshot.project_id = "project-a"
        hinted_run = AgentRun(
            id="codex-session:failed-promotion",
            harness="codex",
            process_or_session="failed hook",
            state="running",
            observation_target="/project-a",
            observation_project_id="project-a",
            branch="main",
            issue_id=None,
            issue_reference_hint="owner/repository#15",
        )

        collector = WorkspaceCollector(
            [current_project],
            factory=lambda _project, **_kwargs: FakeProjectCollector(
                current_snapshot
            ),
            agent_observer=lambda _targets: ([hinted_run], []),
            binding_promoter=lambda promotion: (
                False,
                Diagnostic(
                    promotion.agent_run_id,
                    "warning",
                    "record changed",
                    "agent-issue-binding-race",
                ),
            ),
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual({"I_not_persisted": []}, snapshot.issue_runs)
        self.assertIsNone(snapshot.agent_runs[0].issue_id)
        self.assertEqual("agent-issue-binding-race", snapshot.diagnostics[0].code)

    def test_grouped_clone_target_collects_project_once(self) -> None:
        grouped = ResolvedProject(
            "project:example",
            "Example",
            "repository:example",
            ("personal",),
            ("/clone-one", "/clone-two"),
            "/clone-one",
        )
        factory_calls: list[ResolvedProject] = []

        def factory(current_target, **_kwargs):
            factory_calls.append(current_target)
            return FakeProjectCollector(project_snapshot("/clone-one"))

        collector = WorkspaceCollector(
            [grouped],
            factory=factory,
            agent_observer=lambda _targets: ([], []),
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual([grouped], factory_calls)
        self.assertEqual(1, len(snapshot.projects))

    def test_one_failed_project_does_not_blank_the_workspace(self) -> None:
        good_snapshot = project_snapshot("/good")

        def factory(current_target, **_kwargs):
            if current_target.primary_anchor == "/bad":
                raise RuntimeError("fixture failure")
            return FakeProjectCollector(good_snapshot)

        collector = WorkspaceCollector(
            [
                resolved_project("/good", "project:good"),
                resolved_project("/bad", "project:bad"),
            ],
            factory=factory,
            agent_observer=lambda _targets: ([], []),
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual(
            ["fresh", "unavailable"],
            [project.status for project in snapshot.projects],
        )
        self.assertIn("fixture failure", snapshot.projects[1].diagnostics[0].message)

    def test_agent_observer_failure_does_not_blank_projects(self) -> None:
        collector = WorkspaceCollector(
            [resolved_project()],
            factory=lambda _project, **_kwargs: FakeProjectCollector(
                project_snapshot()
            ),
            agent_observer=lambda _targets: (_ for _ in ()).throw(
                RuntimeError("agent observation crashed")
            ),
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual(1, len(snapshot.projects))
        self.assertIsNotNone(snapshot.projects[0].snapshot)
        self.assertEqual([], snapshot.agent_runs)
        self.assertEqual("agent-observation", snapshot.diagnostics[0].code)

    def test_overlapping_refreshes_are_serialized(self) -> None:
        active = 0
        maximum_active = 0
        counter_lock = threading.Lock()
        good_snapshot = project_snapshot()

        class SlowCollector:
            def refresh(self) -> ProjectSnapshot:
                nonlocal active, maximum_active
                with counter_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.03)
                with counter_lock:
                    active -= 1
                return good_snapshot

        collector = WorkspaceCollector(
            [resolved_project()],
            factory=lambda _target, **_kwargs: SlowCollector(),  # type: ignore[arg-type]
            agent_observer=lambda _targets: ([], []),
        )
        results: list[ProjectSnapshot] = []

        def refresh() -> None:
            results.append(collector.refresh().projects[0].snapshot)  # type: ignore[arg-type]

        with mock.patch.object(Path, "is_dir", return_value=True):
            first = threading.Thread(target=refresh)
            second = threading.Thread(target=refresh)
            first.start()
            second.start()
            first.join()
            second.join()

        self.assertEqual(1, maximum_active)
        self.assertEqual(2, len(results))


if __name__ == "__main__":
    unittest.main()
