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
    observe_hook_runs,
    process_info,
    publish_hook_event,
    write_hook_record,
)
from dashpot.collect import ProjectCollector, WorkspaceCollector, discover_project_targets
from dashpot.issue_sources import IssueSource
from dashpot.model import (
    AgentRun,
    Diagnostic,
    ProjectSnapshot,
    ProjectTarget,
    Repository,
    WorkspaceEntry,
    Worktree,
)
from dashpot.repository import parse_worktrees


ROOT = Path(__file__).resolve().parents[1]
ISSUE_FIXTURE = json.loads(
    (ROOT / "conformance" / "issue" / "fixtures" / "github.json").read_text()
)


def repository(root: str = "/repo") -> Repository:
    return Repository(
        root,
        Path(root).name,
        "main",
        "abc123",
        False,
        [Worktree(root, "abc123", "main")],
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


class RepositoryTests(unittest.TestCase):
    def test_worktree_parser_keeps_branch_and_detached_state(self) -> None:
        raw = """worktree /repo
HEAD abc123
branch refs/heads/main

worktree /repo-worktree
HEAD def456
detached
"""

        result = parse_worktrees(raw)

        self.assertEqual("main", result[0].branch)
        self.assertIsNone(result[1].branch)


class ProjectCollectorTests(unittest.TestCase):
    def test_combines_declared_and_observed_state(self) -> None:
        observed = AgentRun(
            "codex-session:1",
            "codex",
            "1 hook",
            "running",
            "/repo",
            "/repo",
            "main",
            "example/project#7",
        )
        collector = ProjectCollector(
            Path("/repo"),
            FakeSource(),
            repository_observer=lambda _root: repository(),
            agent_observer=lambda _repository: ([observed], [Diagnostic("agent", "info", "ok")]),
        )

        snapshot = collector.refresh()

        self.assertEqual(
            ["codex-session:1"], snapshot.issue_runs["I_example/project#7"]
        )
        self.assertEqual("Build observer", snapshot.issues[0]["title"])
        self.assertEqual([observed], snapshot.agent_runs)
        self.assertEqual("agent", snapshot.diagnostics[0].source)


class HookObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, session_id: str, state: str, process: ProcessIdentity | None = None) -> None:
        write_hook_record(
            {
                "version": 1,
                "sessionId": session_id,
                "harness": "codex",
                "state": state,
                "cwd": "/repo",
                "repositoryRoot": "/repo",
                "branch": "main",
                "declaredIssueReference": "example/project#7",
                "event": "Stop" if state == "waiting" else "PreToolUse",
                "lastActivityAt": "2026-08-24T15:00:00Z",
                "sessionProcess": process.as_record() if process else None,
            },
            self.state_dir,
        )

    def test_live_record_is_returned(self) -> None:
        self.write("live", "waiting", self.process)

        runs, diagnostics = observe_hook_runs(
            repository(),
            self.state_dir,
            lookup=lambda _pid: self.process,
            isolated=False,
        )

        self.assertEqual("waiting", runs[0].state)
        self.assertEqual("example/project#7", runs[0].declared_issue_reference)
        self.assertEqual([], diagnostics)

    def test_ended_and_orphaned_records_are_not_active(self) -> None:
        self.write("ended", "ended", self.process)
        self.write("orphaned", "running", self.process)

        runs, diagnostics = observe_hook_runs(
            repository(),
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
            repository(),
            self.state_dir,
            lookup=lambda _pid: None,
            isolated=True,
        )

        self.assertEqual("unknown", runs[0].state)
        self.assertIn("liveness is unknown", diagnostics[0].message)

    def test_malformed_record_becomes_diagnostic(self) -> None:
        (self.state_dir / "bad.json").write_text(json.dumps({"version": 99}))

        runs, diagnostics = observe_hook_runs(repository(), self.state_dir)

        self.assertEqual([], runs)
        self.assertIn("unsupported record", diagnostics[0].message)

    def test_resume_event_preserves_initial_issue_binding(self) -> None:
        base_event = {
            "session_id": "resume-me",
            "cwd": "/repo",
            "hook_event_name": "SessionStart",
        }
        publish_hook_event(
            base_event,
            self.state_dir,
            environ={"DASHPOT_ISSUE_REF": "example/project#7"},
            process=self.process,
        )

        publish_hook_event(
            {**base_event, "hook_event_name": "Stop"},
            self.state_dir,
            environ={},
            process=self.process,
        )

        record = json.loads((self.state_dir / "resume-me.json").read_text())
        self.assertEqual("example/project#7", record["declaredIssueReference"])
        self.assertEqual("waiting", record["state"])

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
    def test_one_failed_project_does_not_blank_the_workspace(self) -> None:
        good_snapshot = ProjectSnapshot(
            "2026-08-24T15:00:00Z",
            "fresh",
            "2026-08-24T15:00:00Z",
            "2026-08-24T15:00:00Z",
            repository("/good"),
            [issue()],
            {"I_example/project#7": []},
            [],
            [],
        )

        def factory(root, **_kwargs):
            if root == Path("/bad"):
                raise RuntimeError("fixture failure")
            return FakeProjectCollector(good_snapshot)

        collector = WorkspaceCollector(
            [
                ProjectTarget("test", "good", "/good"),
                ProjectTarget("test", "bad", "/bad"),
            ],
            factory=factory,
        )

        with mock.patch.object(Path, "is_dir", return_value=True):
            snapshot = collector.refresh()

        self.assertEqual(
            ["fresh", "unavailable"],
            [project.status for project in snapshot.projects],
        )
        self.assertIn("fixture failure", snapshot.projects[1].diagnostics[0].message)

    def test_discovers_marked_root_and_immediate_child_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".dashpot.json").write_text("{}")
            child = root / "child"
            child.mkdir()
            (child / ".dashpot.json").write_text("{}")
            nested = child / "nested"
            nested.mkdir()
            (nested / ".dashpot.json").write_text("{}")

            targets = discover_project_targets(
                [WorkspaceEntry("one", str(root)), WorkspaceEntry("duplicate", str(root))]
            )

        self.assertEqual([".", "child"], [target.repository for target in targets])

    def test_overlapping_refreshes_are_serialized(self) -> None:
        active = 0
        maximum_active = 0
        counter_lock = threading.Lock()
        good_snapshot = ProjectSnapshot(
            "2026-08-24T15:00:00Z",
            "fresh",
            "2026-08-24T15:00:00Z",
            "2026-08-24T15:00:00Z",
            repository("/repo"),
            [issue()],
            {"I_example/project#7": []},
            [],
            [],
        )

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
            [ProjectTarget("test", "repo", "/repo")],
            factory=lambda _root, **_kwargs: SlowCollector(),  # type: ignore[arg-type]
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
