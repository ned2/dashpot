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
    ProcessIdentity,
    nearest_codex_process,
    observe_agent_runs,
    observe_hook_runs,
    process_info,
    publish_hook_event,
    session_directory,
    write_hook_record,
)
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
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
    number_text = reference.rpartition("#")[2]
    if number_text.isdigit() and int(number_text) > 0:
        value["number"] = int(number_text)
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
        self.assertEqual(complete["number"], serialized["number"])
        self.assertNotIn("number", serialized["origin"])
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
        self.assertIsNone(runs[0].issue_reference_hint)
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

    def test_global_issue_binding_is_rejected_not_combined(self) -> None:
        self.write("globally-bound", "waiting", self.process)
        path = self.state_dir / "globally-bound.json"
        record = json.loads(path.read_text())
        record["issueId"] = "I_global"
        record["issueReferenceHint"] = "example/project#7"
        path.write_text(json.dumps(record))

        runs, diagnostics = observe_hook_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual(1, len(runs))
        self.assertIsNone(runs[0].issue_id)
        self.assertIsNone(runs[0].issue_reference_hint)
        self.assertEqual(
            "agent-global-binding-rejected", diagnostics[0].code
        )
        self.assertIn("dashpot work start", diagnostics[0].message)

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

    def test_interrupt_event_publishes_a_waiting_record(self) -> None:
        publish_hook_event(
            {
                "session_id": "interrupted",
                "cwd": "/repo",
                "hook_event_name": "Interrupt",
            },
            self.state_dir,
            environ={},
            process=self.process,
        )

        record = json.loads((self.state_dir / "interrupted.json").read_text())
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


class HookRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state_dir = self.root / "global"
        self.state_dir.mkdir()
        self.worktree = self.root / "repo"
        self.worktree.mkdir()
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record(self, state: str, last_activity_at: str) -> dict:
        return {
            "version": 2,
            "sessionId": "routed",
            "harness": "codex",
            "state": state,
            "cwd": str(self.worktree),
            "repositoryRoot": str(self.worktree),
            "branch": "main",
            "event": "Stop" if state == "waiting" else "PreToolUse",
            "lastActivityAt": last_activity_at,
            "sessionProcess": self.process.as_record(),
        }

    def targets(self) -> dict[str, list[ObservationTarget]]:
        return {"project:example": [observation_target(str(self.worktree))]}

    def test_publish_routes_to_a_configured_projects_local_store(self) -> None:
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=self.worktree, check=True)
        (self.worktree / ".dashpot").mkdir()
        (self.worktree / ".dashpot" / "config.json").write_text("{}")

        written = publish_hook_event(
            {
                "session_id": "routed",
                "cwd": str(self.worktree),
                "hook_event_name": "Stop",
            },
            environ={},
            process=self.process,
        )

        self.assertEqual(session_directory(self.worktree), written.parent)

    def test_publish_falls_back_to_the_global_store_when_unconfigured(
        self,
    ) -> None:
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=self.worktree, check=True)

        with mock.patch(
            "dashpot.agents.state_directory", return_value=self.state_dir
        ):
            written = publish_hook_event(
                {
                    "session_id": "routed",
                    "cwd": str(self.worktree),
                    "hook_event_name": "Stop",
                },
                environ={},
                process=self.process,
            )

        self.assertEqual(self.state_dir, written.parent)
        self.assertFalse((self.worktree / ".dashpot").exists())

    def test_project_local_records_are_observed(self) -> None:
        write_hook_record(
            self.record("waiting", "2026-08-24T15:00:00Z"),
            session_directory(self.worktree),
        )

        runs, diagnostics = observe_hook_runs(
            self.targets(),
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("codex-session:routed", runs[0].id)
        self.assertEqual("waiting", runs[0].state)

    def test_freshest_record_wins_when_a_session_exists_in_both_stores(
        self,
    ) -> None:
        write_hook_record(
            self.record("running", "2026-08-24T14:00:00Z"), self.state_dir
        )
        write_hook_record(
            self.record("waiting", "2026-08-24T15:00:00Z"),
            session_directory(self.worktree),
        )

        runs, diagnostics = observe_hook_runs(
            self.targets(),
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(1, len(runs))
        self.assertEqual("waiting", runs[0].state)
        self.assertEqual("2026-08-24T15:00:00Z", runs[0].last_activity_at)


class WorkObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state_dir = self.root / "hooks"
        self.state_dir.mkdir()
        self.worktree = self.root / "repo"
        self.worktree.mkdir()
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record_work(
        self,
        worktree: Path,
        *,
        session_key: str = "codex-42-abcd1234",
        process: ProcessIdentity | None = None,
    ) -> ActiveWork:
        process = process or self.process
        work = ActiveWork(
            session_key=session_key,
            harness="codex",
            session_label=f"codex pid {process.pid}",
            session_process=SessionProcess(process.pid, process.started_at),
            issue_id="I_example/project#7",
            issue_reference="example/project#7",
            binding_provenance="explicit-reference",
            started_at="2026-08-24T14:00:00Z",
            working_directory=str(worktree),
            branch="feature",
        )
        WorkStore(worktree).start(work)
        return work

    def write_hook(self, session_id: str, state: str, cwd: str) -> None:
        write_hook_record(
            {
                "version": 2,
                "sessionId": session_id,
                "harness": "codex",
                "state": state,
                "cwd": cwd,
                "repositoryRoot": cwd,
                "branch": "main",
                "event": "Stop" if state == "waiting" else "PreToolUse",
                "lastActivityAt": "2026-08-24T15:00:00Z",
                "sessionProcess": self.process.as_record(),
            },
            self.state_dir,
        )

    def targets(self) -> dict[str, list[ObservationTarget]]:
        return {"project:example": [observation_target(str(self.worktree))]}

    def test_work_run_correlates_hook_session_state_by_process(self) -> None:
        work = self.record_work(self.worktree)
        self.write_hook("session-a", "waiting", str(self.worktree))

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(1, len(runs))
        self.assertEqual(work.run_id, runs[0].id)
        self.assertEqual("I_example/project#7", runs[0].issue_id)
        self.assertEqual("waiting", runs[0].state)
        self.assertEqual("2026-08-24T15:00:00Z", runs[0].last_activity_at)
        self.assertEqual("feature", runs[0].branch)

    def test_work_run_without_hook_session_has_unknown_state(self) -> None:
        work = self.record_work(self.worktree)

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("unknown", runs[0].state)
        self.assertEqual(work.started_at, runs[0].last_activity_at)

    def test_orphaned_work_record_is_skipped_with_warning(self) -> None:
        self.record_work(self.worktree)

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=lambda _pid: None,
            isolated=False,
        )

        self.assertEqual([], runs)
        self.assertEqual("work-session-orphaned", diagnostics[0].code)

    def test_hook_session_without_work_record_stays_listed_unbound(self) -> None:
        self.write_hook("session-b", "running", str(self.worktree))

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("codex-session:session-b", runs[0].id)
        self.assertIsNone(runs[0].issue_id)
        self.assertEqual("running", runs[0].state)

    def test_one_session_recorded_at_two_worktrees_is_a_conflict(self) -> None:
        other = self.root / "repo-linked"
        other.mkdir()
        self.record_work(self.worktree)
        self.record_work(other)

        runs, diagnostics = observe_agent_runs(
            {
                "project:example": [
                    observation_target(str(self.worktree)),
                    observation_target(str(other)),
                ]
            },
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual(2, len(runs))
        self.assertEqual("work-session-conflict", diagnostics[0].code)

    def test_unavailable_target_work_records_are_not_read(self) -> None:
        self.record_work(self.worktree)
        target = observation_target(str(self.worktree))
        target.availability = "unavailable"

        runs, diagnostics = observe_agent_runs(
            {"project:example": [target]},
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual([], runs)
        self.assertEqual([], diagnostics)


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

    def test_unbound_hinted_run_stays_unbound_without_promotion(self) -> None:
        current_project = resolved_project("/project-a", "project-a")
        current_issue = issue("owner/repository#15")
        current_issue["id"] = "I_observed"
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
            issue_reference_hint=None,
        )

        collector = WorkspaceCollector(
            [current_project],
            factory=lambda _project, **_kwargs: FakeProjectCollector(
                current_snapshot
            ),
            agent_observer=lambda _targets: ([hinted_run], []),
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual({"I_observed": []}, snapshot.issue_runs)
        self.assertIsNone(snapshot.agent_runs[0].issue_id)
        self.assertEqual([], snapshot.diagnostics)

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
