from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import threading
import time
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from unittest import mock

from typing_extensions import override

from dashpot.agents import (
    HookRecordStore,
    ProcessAbsent,
    ProcessIdentity,
    ProcessPresent,
    ProcessUnobservable,
    host_process_lookup,
    nearest_codex_process,
    now_iso,
    observe_agent_runs,
    publish_hook_event,
    session_directory,
    write_hook_record,
)
from dashpot.collect import ObservationCoordinator, ProjectCollector
from dashpot.commands import CommandResult
from dashpot.issue_profile import conform_issue
from dashpot.issue_sources import IssueSource, IssueSourceObservation
from dashpot.model import (
    AgentRun,
    Branch,
    Diagnostic,
    Issue,
    IssueActivity,
    LinkedPullRequest,
    ObservationTarget,
    ObservationTargetInventory,
    ProjectSnapshot,
    ResolvedProject,
)
from dashpot.repository import BranchObservation, observe_github_repository_identity
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
from helpers import absent, jsonable, present, snapshot_of, table_lookup, unobservable

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
        "main",
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
    root: str = "/repo", issues: list[Issue] | None = None
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


def issue(reference: str = "example/project#7") -> Issue:
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
    @override
    def name(self) -> str:
        return "fake"

    @override
    def _collect(self) -> list[Issue]:
        return [issue()]


class EmptySource(IssueSource):
    @property
    @override
    def name(self) -> str:
        return "empty"

    @override
    def _collect(self) -> list[Issue]:
        return []


class PaletteSource(FakeSource):
    @override
    def _collect_label_colors(self) -> dict[str, str]:
        return {"enhancement": "a2eeef"}

    @override
    def _collect_issue_activity(self) -> dict[str, IssueActivity]:
        return {
            issue()["id"]: IssueActivity(
                comment_count=2,
                linked_pull_requests=[
                    LinkedPullRequest(41, "https://example.test/pull/41", "merged")
                ],
            )
        }


class CountingSource(FakeSource):
    def __init__(self) -> None:
        super().__init__()
        self.collection_count = 0

    @override
    def _collect(self) -> list[Issue]:
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
        self.assertEqual({}, snapshot.label_colors)

    def test_branches_travel_with_the_targets_half_of_the_snapshot(self) -> None:
        branch = Branch(
            refname="refs/heads/main",
            name="main",
            remote=None,
            head="abc123",
            committed_at="2026-08-27T00:00:00Z",
        )
        anchors_seen: list[list[Path]] = []

        def observe_branches(anchors: Sequence[Path]) -> BranchObservation:
            anchors_seen.append(list(anchors))
            return BranchObservation([branch], "2026-08-27T01:00:00Z", [])

        collector = ProjectCollector(
            resolved_project(),
            FakeSource(),
            target_observer=lambda _anchors: target_inventory(),
            branch_observer=observe_branches,
        )

        snapshot = collector.refresh()
        inventory = collector.observe_targets()

        self.assertEqual([[Path("/repo")], [Path("/repo")]], anchors_seen)
        self.assertEqual([branch], snapshot.branches)
        self.assertEqual("2026-08-27T01:00:00Z", snapshot.fetched_at)
        self.assertEqual([branch], inventory.branches)
        self.assertEqual("2026-08-27T01:00:00Z", inventory.fetched_at)
        payload = jsonable(snapshot)
        self.assertEqual("refs/heads/main", payload["branches"][0]["refname"])
        self.assertEqual("2026-08-27T01:00:00Z", payload["fetchedAt"])

    def test_source_label_palette_travels_with_the_snapshot(self) -> None:
        collector = ProjectCollector(
            resolved_project(),
            PaletteSource(),
            target_observer=lambda _anchors: target_inventory(),
        )

        snapshot = collector.refresh()

        self.assertEqual({"enhancement": "a2eeef"}, snapshot.label_colors)
        self.assertEqual({"enhancement": "a2eeef"}, jsonable(snapshot)["labelColors"])
        activity = jsonable(snapshot)["issueActivity"][issue()["id"]]
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

        serialized = jsonable(snapshot)["issues"][0]

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
            "linked",
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
            jsonable(snapshot)["observationTargets"][0]["path"],
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
            target_observer=lambda _anchors: ObservationTargetInventory([target], []),
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
    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    @override
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

    def test_the_freshest_record_wins_whatever_its_stamp_precision(self) -> None:
        # The same session is recorded globally and Project-locally around an
        # integration upgrade. A whole-second stamp is not an older one.
        worktree = Path(self.temporary.name) / "repo"
        local = session_directory(worktree)
        local.mkdir(parents=True)
        record = {
            "version": 2,
            "sessionId": "twice",
            "harness": "codex",
            "state": "waiting",
            "cwd": str(worktree),
            "repositoryRoot": str(worktree),
            "branch": "main",
            "event": "Stop",
            "lastActivityAt": "2026-08-24T15:00:00Z",
            "sessionProcess": self.process.as_record(),
        }
        write_hook_record(record, self.state_dir)
        write_hook_record(
            {**record, "lastActivityAt": "2026-08-24T15:00:00.500000Z"}, local
        )

        runs, _diagnostics = observe_agent_runs(
            {"project:example": [observation_target(str(worktree))]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual(1, len(runs))
        self.assertEqual("2026-08-24T15:00:00.500000Z", runs[0].last_activity_at)

    def test_the_turn_clock_is_carried_while_running_and_cleared_on_stop(
        self,
    ) -> None:
        def record(state: str, stamp: str) -> dict[str, object]:
            return {
                "version": 2,
                "sessionId": "turns",
                "harness": "codex",
                "state": state,
                "cwd": "/repo",
                "repositoryRoot": "/repo",
                "branch": "main",
                "event": "UserPromptSubmit" if state == "running" else "Stop",
                "lastActivityAt": stamp,
                "sessionProcess": self.process.as_record(),
            }

        def stored() -> dict[str, object]:
            path = self.state_dir / "turns.json"
            return cast("dict[str, object]", json.loads(path.read_text()))

        write_hook_record(
            record("running", "2026-08-24T15:00:00.000000Z"), self.state_dir
        )
        self.assertEqual("2026-08-24T15:00:00.000000Z", stored()["turnStartedAt"])

        # Later events in the same turn do not restart its clock.
        write_hook_record(
            record("running", "2026-08-24T15:04:00.000000Z"), self.state_dir
        )
        self.assertEqual("2026-08-24T15:00:00.000000Z", stored()["turnStartedAt"])

        # The turn ends, and a waiting session has no turn in flight.
        write_hook_record(
            record("waiting", "2026-08-24T15:05:00.000000Z"), self.state_dir
        )
        self.assertIsNone(stored()["turnStartedAt"])

        # The next turn starts its own clock.
        write_hook_record(
            record("running", "2026-08-24T15:09:00.000000Z"), self.state_dir
        )
        self.assertEqual("2026-08-24T15:09:00.000000Z", stored()["turnStartedAt"])

    def test_stamps_are_fixed_width_so_records_order_by_text_too(self) -> None:
        self.assertRegex(now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")

    def test_live_record_is_returned(self) -> None:
        self.write("live", "waiting", self.process)

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
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

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target(), linked]},
            self.state_dir,
            lookup=present(self.process),
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

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], runs)
        self.assertEqual("agent-target-mismatch", diagnostics[0].code)

    def test_ended_and_gone_unbound_records_are_not_active_or_diagnosed(
        self,
    ) -> None:
        self.write("ended", "ended", self.process)
        self.write("gone", "running", self.process)

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=absent(),
        )

        self.assertEqual([], runs)
        self.assertEqual([], diagnostics)

    def test_pid_reused_by_a_different_process_is_gone(self) -> None:
        self.write("reused", "running", self.process)
        newcomer = ProcessIdentity(42, 1, "codex", "Wed Aug 26 09:00:00 2026")

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(newcomer),
        )

        self.assertEqual([], runs)
        self.assertEqual([], diagnostics)

    def test_live_process_with_same_identity_keeps_recorded_state(self) -> None:
        self.write("waiting-live", "waiting", self.process)
        self.write("running-live", "running", self.process)

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(
            {
                "codex-session:waiting-live": "waiting",
                "codex-session:running-live": "running",
            },
            {run.id: run.state for run in runs},
        )

    def test_unobservable_process_degrades_to_unknown_never_exited(self) -> None:
        for reason in (
            "isolated-namespace",
            "ps-unavailable",
            "ps-timeout",
            "ps-failed",
            "ps-unparseable",
            "kill-failed",
        ):
            with self.subTest(reason=reason):
                self.write("sandboxed", "running", self.process)
                self.write("sandboxed-too", "waiting", self.process)

                runs, diagnostics = observe_agent_runs(
                    {"project:example": [observation_target()]},
                    self.state_dir,
                    lookup=unobservable(reason),
                )

                self.assertEqual({"unknown"}, {run.state for run in runs})
                self.assertEqual(2, len(runs))
                self.assertEqual(1, len(diagnostics))
                self.assertEqual("agent-session-liveness-unknown", diagnostics[0].code)
                self.assertEqual("info", diagnostics[0].severity)
                self.assertIn(reason, diagnostics[0].message)
                self.assertNotIn("exited", diagnostics[0].message)

    def test_graceful_session_end_removes_the_record(self) -> None:
        event = {"session_id": "graceful", "cwd": "/repo", "hook_event_name": "Stop"}
        publish_hook_event(event, self.state_dir, environ={}, process=self.process)
        self.assertTrue((self.state_dir / "graceful.json").exists())

        publish_hook_event(
            {**event, "hook_event_name": "SessionEnd"},
            self.state_dir,
            environ={},
            process=self.process,
        )

        self.assertFalse((self.state_dir / "graceful.json").exists())
        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )
        self.assertEqual([], runs)
        self.assertEqual([], diagnostics)

    def test_session_end_with_a_malformed_binding_still_removes_the_record(
        self,
    ) -> None:
        self.write("ending", "waiting", self.process)

        write_hook_record(
            {
                "version": 2,
                "sessionId": "ending",
                "state": "ended",
                "issueId": "not an id",
            },
            self.state_dir,
        )

        self.assertFalse((self.state_dir / "ending.json").exists())

    def test_observation_prunes_gone_and_ended_records_but_keeps_live_ones(
        self,
    ) -> None:
        self.write("ended", "ended", self.process)
        self.write("gone", "running", self.process)
        self.write("live", "running", self.process)
        gone_process = ProcessIdentity(43, 1, "codex", "Tue Aug 25 03:00:00 2026")
        (self.state_dir / "gone.json").write_text(
            json.dumps(
                {
                    **json.loads((self.state_dir / "gone.json").read_text()),
                    "sessionProcess": gone_process.as_record(),
                }
            )
        )

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=table_lookup({42: self.process}),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(["codex-session:live"], [run.id for run in runs])
        self.assertFalse((self.state_dir / "ended.json").exists())
        self.assertFalse((self.state_dir / "gone.json").exists())
        self.assertTrue((self.state_dir / "live.json").exists())
        self.assertTrue((self.state_dir / ".live.lock").exists())
        self.assertFalse((self.state_dir / ".gone.lock").exists())
        self.assertFalse((self.state_dir / ".ended.lock").exists())

    def test_observation_reclaims_lock_files_that_guard_no_record(self) -> None:
        self.write("live", "running", self.process)
        (self.state_dir / ".orphaned.lock").touch()
        (self.state_dir / ".not a session id.lock").touch()

        observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=table_lookup({42: self.process}),
        )

        self.assertFalse((self.state_dir / ".orphaned.lock").exists())
        self.assertTrue((self.state_dir / ".live.lock").exists())
        self.assertTrue((self.state_dir / ".not a session id.lock").exists())

    def test_prune_lock_keeps_the_lock_of_an_existing_record(self) -> None:
        self.write("live", "running", self.process)
        store = HookRecordStore(self.state_dir)

        self.assertFalse(store.prune_lock("live"))
        self.assertTrue((self.state_dir / ".live.lock").exists())

        (self.state_dir / "live.json").unlink()
        self.assertEqual(["live"], store.orphaned_locks())
        self.assertTrue(store.prune_lock("live"))
        self.assertFalse((self.state_dir / ".live.lock").exists())

    def test_prune_is_conditional_on_the_observed_record(self) -> None:
        self.write("stale", "running", self.process)
        path = self.state_dir / "stale.json"
        observed = json.loads(path.read_text())
        store = HookRecordStore(self.state_dir)

        updated = {**observed, "lastActivityAt": "2026-08-24T16:00:00Z"}
        path.write_text(json.dumps(updated))
        self.assertFalse(store.prune("stale", observed))
        self.assertTrue(path.exists())

        self.assertTrue(store.prune("stale", updated))
        self.assertFalse(path.exists())
        self.assertFalse(store.prune("stale", updated))

    def test_malformed_record_becomes_diagnostic(self) -> None:
        (self.state_dir / "bad.json").write_text(json.dumps({"version": 99}))

        runs, diagnostics = observe_agent_runs(
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

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual(1, len(runs))
        self.assertIsNone(runs[0].issue_id)
        self.assertIsNone(runs[0].issue_reference_hint)
        self.assertEqual("agent-global-binding-rejected", diagnostics[0].code)
        self.assertIn("dashpot work start", diagnostics[0].message)

    def test_claude_code_record_is_observed_with_its_own_identity(self) -> None:
        claude = ProcessIdentity(77, 1, "claude", "Tue Aug 25 02:00:00 2026")
        write_hook_record(
            {
                "version": 2,
                "sessionId": "claude-live",
                "harness": "claude-code",
                "state": "running",
                "cwd": "/repo",
                "repositoryRoot": "/repo",
                "branch": "main",
                "event": "UserPromptSubmit",
                "lastActivityAt": "2026-08-24T15:00:00Z",
                "sessionProcess": claude.as_record(),
            },
            self.state_dir,
        )

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(claude),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("claude-code-session:claude-live", runs[0].id)
        self.assertEqual("claude-code", runs[0].harness)
        self.assertEqual("running", runs[0].state)

    def test_codex_and_claude_code_sessions_coexist_at_one_worktree(
        self,
    ) -> None:
        claude = ProcessIdentity(77, 1, "claude", "Tue Aug 25 02:00:00 2026")
        lookup = {42: self.process, 77: claude}
        self.write("codex-live", "waiting", self.process)
        write_hook_record(
            {
                "version": 2,
                "sessionId": "claude-live",
                "harness": "claude-code",
                "state": "running",
                "cwd": "/repo",
                "repositoryRoot": "/repo",
                "branch": "main",
                "event": "UserPromptSubmit",
                "lastActivityAt": "2026-08-24T15:00:00Z",
                "sessionProcess": claude.as_record(),
            },
            self.state_dir,
        )

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=table_lookup(lookup),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(
            {"claude-code-session:claude-live", "codex-session:codex-live"},
            {run.id for run in runs},
        )

    def test_unsupported_harness_record_becomes_a_diagnostic(self) -> None:
        write_hook_record(
            {
                "version": 2,
                "sessionId": "mystery",
                "harness": "cursor",
                "state": "running",
                "cwd": "/repo",
                "repositoryRoot": "/repo",
                "event": "UserPromptSubmit",
                "sessionProcess": None,
            },
            self.state_dir,
        )

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]}, self.state_dir
        )

        self.assertEqual([], runs)
        self.assertIn("unsupported harness", diagnostics[0].message)

    def test_record_session_must_match_filename(self) -> None:
        self.write("actual-session", "waiting", self.process)
        (self.state_dir / "actual-session.json").rename(
            self.state_dir / "different-session.json"
        )

        runs, diagnostics = observe_agent_runs(
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

    def test_nearest_agent_process_prefers_the_nearest_harness(self) -> None:
        from dashpot.agents import nearest_agent_process

        shell = ProcessIdentity(10, 20, "bash", "Tue Aug 25 01:00:00 2026")
        claude = ProcessIdentity(20, 30, "claude", "Tue Aug 25 00:59:00 2026")
        codex = ProcessIdentity(30, 1, "codex", "Tue Aug 25 00:58:00 2026")
        chain = {10: shell, 20: claude, 30: codex}

        with mock.patch("dashpot.agents.os.getppid", return_value=10):
            result = nearest_agent_process(lookup=table_lookup(chain))

        self.assertEqual(("claude-code", claude), result)

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
            result = nearest_codex_process(lookup=table_lookup({10: sandbox, 20: host}))

        self.assertEqual(host, result)

    def test_host_process_lookup_parses_portable_ps_fields_and_arguments(
        self,
    ) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=(
                "42 1 codex Tue Aug 25 01:00:00 2026 "
                "/opt/codex exec --sandbox workspace-write\n"
            ),
        )

        with (
            mock.patch(
                "dashpot.agents.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.agents.os.kill") as kill,
            mock.patch("dashpot.agents.subprocess.run", return_value=completed) as run,
        ):
            result = host_process_lookup(42)

        self.assertEqual(
            ProcessPresent(
                ProcessIdentity(
                    42,
                    1,
                    "codex",
                    "Tue Aug 25 01:00:00 2026",
                    "/opt/codex exec --sandbox workspace-write",
                )
            ),
            result,
        )
        kill.assert_called_once_with(42, 0)
        arguments = run.call_args.args[0]
        self.assertEqual(5, arguments.count("-o"))
        self.assertEqual("C", run.call_args.kwargs["env"]["LC_ALL"])
        self.assertEqual("UTC", run.call_args.kwargs["env"]["TZ"])

    def test_host_process_lookup_reports_a_missing_pid_as_absent(self) -> None:
        with (
            mock.patch(
                "dashpot.agents.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.agents.os.kill", side_effect=ProcessLookupError),
            mock.patch("dashpot.agents.subprocess.run") as run,
        ):
            result = host_process_lookup(42)

        self.assertEqual(ProcessAbsent(42), result)
        run.assert_not_called()

    def test_host_process_lookup_treats_another_users_process_as_present(
        self,
    ) -> None:
        completed = mock.Mock(
            returncode=0, stdout="42 1 codex Tue Aug 25 01:00:00 2026\n"
        )

        with (
            mock.patch(
                "dashpot.agents.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.agents.os.kill", side_effect=PermissionError),
            mock.patch("dashpot.agents.subprocess.run", return_value=completed),
        ):
            result = host_process_lookup(42)

        self.assertEqual(
            ProcessPresent(ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")),
            result,
        )

    def test_host_process_lookup_reports_every_probe_failure_as_unobservable(
        self,
    ) -> None:
        cases: list[tuple[str, Any]] = [
            ("ps-unavailable", FileNotFoundError("ps")),
            ("ps-timeout", subprocess.TimeoutExpired(["ps"], 2)),
            ("ps-failed", mock.Mock(returncode=1, stdout="")),
            ("ps-unparseable", mock.Mock(returncode=0, stdout="garbage\n")),
            ("ps-unparseable", mock.Mock(returncode=0, stdout="x y z a b c d e f\n")),
        ]
        for reason, outcome in cases:
            with self.subTest(reason=reason, outcome=outcome):
                run_kwargs = (
                    {"side_effect": outcome}
                    if isinstance(outcome, BaseException)
                    else {"return_value": outcome}
                )
                with (
                    mock.patch(
                        "dashpot.agents.process_namespace_is_isolated",
                        return_value=False,
                    ),
                    mock.patch("dashpot.agents.os.kill"),
                    mock.patch("dashpot.agents.subprocess.run", **run_kwargs),
                ):
                    result = host_process_lookup(42)

                self.assertEqual(ProcessUnobservable(42, reason), result)

        with (
            mock.patch(
                "dashpot.agents.process_namespace_is_isolated", return_value=False
            ),
            mock.patch("dashpot.agents.os.kill", side_effect=OSError("EINVAL")),
            mock.patch("dashpot.agents.subprocess.run") as run,
        ):
            self.assertEqual(
                ProcessUnobservable(42, "kill-failed"), host_process_lookup(42)
            )
        run.assert_not_called()

    def test_host_process_lookup_never_probes_an_isolated_namespace(self) -> None:
        with (
            mock.patch(
                "dashpot.agents.process_namespace_is_isolated", return_value=True
            ),
            mock.patch("dashpot.agents.os.kill") as kill,
            mock.patch("dashpot.agents.subprocess.run") as run,
        ):
            result = host_process_lookup(42)

        self.assertEqual(ProcessUnobservable(42, "isolated-namespace"), result)
        kill.assert_not_called()
        run.assert_not_called()


class HookRoutingTests(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # The published record carries resolved paths, so the expected
        # Worktree must be resolved too (macOS temp paths are symlinks).
        self.root = Path(self.temporary.name).resolve()
        self.state_dir = self.root / "global"
        self.state_dir.mkdir()
        self.worktree = self.root / "repo"
        self.worktree.mkdir()
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    @override
    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record(self, state: str, last_activity_at: str) -> dict[str, Any]:
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
        subprocess.run(["git", "init", "-q"], cwd=self.worktree, check=True)

        with mock.patch("dashpot.agents.state_directory", return_value=self.state_dir):
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

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=present(self.process),
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

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(1, len(runs))
        self.assertEqual("waiting", runs[0].state)
        self.assertEqual("2026-08-24T15:00:00Z", runs[0].last_activity_at)


class WorkObserverTests(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state_dir = self.root / "hooks"
        self.state_dir.mkdir()
        self.worktree = self.root / "repo"
        self.worktree.mkdir()
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    @override
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
            lookup=present(self.process),
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
            lookup=present(self.process),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("unknown", runs[0].state)
        # Nothing has observed this run doing anything; when its work began
        # is a different fact and is reported as one.
        self.assertIsNone(runs[0].last_activity_at)
        self.assertIsNone(runs[0].turn_started_at)
        self.assertEqual(work.started_at, runs[0].started_at)

    def test_orphaned_work_record_is_one_actionable_diagnostic(self) -> None:
        self.record_work(self.worktree)
        self.write_hook("session-gone", "running", str(self.worktree))

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=absent(),
        )

        self.assertEqual([], runs)
        self.assertEqual(1, len(diagnostics))
        self.assertEqual("work-session-orphaned", diagnostics[0].code)
        self.assertEqual("warning", diagnostics[0].severity)
        self.assertIn("example/project#7", diagnostics[0].message)
        self.assertIn(str(self.worktree), diagnostics[0].message)
        self.assertIn(
            "dashpot work stop --session codex-42-abcd1234", diagnostics[0].message
        )
        self.assertNotIn("exited", diagnostics[0].message)

    def test_observation_reclaims_work_lock_files_that_guard_no_record(
        self,
    ) -> None:
        self.record_work(self.worktree)
        store = WorkStore(self.worktree)
        (store.directory / ".codex-9-zz.lock").touch()

        observe_agent_runs(self.targets(), self.state_dir, lookup=absent())

        self.assertFalse((store.directory / ".codex-9-zz.lock").exists())
        self.assertTrue((store.directory / ".codex-42-abcd1234.lock").exists())

    def test_orphaned_work_survives_observation_until_stopped(self) -> None:
        self.record_work(self.worktree)

        observe_agent_runs(self.targets(), self.state_dir, lookup=absent())

        active, _ = WorkStore(self.worktree).active()
        self.assertEqual(["codex-42-abcd1234"], [work.session_key for work in active])

    def test_unobservable_process_keeps_bound_work_listed_as_unknown(self) -> None:
        for reason in (
            "isolated-namespace",
            "ps-unavailable",
            "ps-timeout",
            "ps-failed",
            "ps-unparseable",
            "kill-failed",
        ):
            with self.subTest(reason=reason):
                work = self.record_work(self.worktree)
                self.write_hook("session-c", "running", str(self.worktree))

                runs, diagnostics = observe_agent_runs(
                    self.targets(),
                    self.state_dir,
                    lookup=unobservable(reason),
                )

                self.assertEqual([work.run_id], [run.id for run in runs])
                self.assertEqual("unknown", runs[0].state)
                self.assertEqual(
                    ["agent-session-liveness-unknown"],
                    [diagnostic.code for diagnostic in diagnostics],
                )
                self.assertNotIn("exited", diagnostics[0].message)

    def test_hook_session_without_work_record_stays_listed_unbound(self) -> None:
        self.write_hook("session-b", "running", str(self.worktree))

        runs, diagnostics = observe_agent_runs(
            self.targets(),
            self.state_dir,
            lookup=present(self.process),
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
            lookup=present(self.process),
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
            lookup=present(self.process),
        )

        self.assertEqual([], runs)
        self.assertEqual([], diagnostics)


class FakeProjectCollector:
    """Serve one prepared snapshot as two independently observed halves."""

    def __init__(self, snapshot: ProjectSnapshot) -> None:
        self.snapshot = snapshot

    def observe_issues(self) -> IssueSourceObservation:
        return IssueSourceObservation(
            status=self.snapshot.issue_source_status,
            attempted_at=self.snapshot.issue_source_attempted_at,
            last_good_at=self.snapshot.issue_source_last_good_at,
            issues=copy.deepcopy(self.snapshot.issues),
            diagnostics=[],
        )

    def observe_targets(self) -> ObservationTargetInventory:
        return ObservationTargetInventory(
            copy.deepcopy(self.snapshot.observation_targets), []
        )


class ObservationCoordinatorTests(unittest.TestCase):
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

        collector = ObservationCoordinator(
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

        collector = ObservationCoordinator(
            [current_project],
            factory=lambda _project, **_kwargs: FakeProjectCollector(current_snapshot),
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

        collector = ObservationCoordinator(
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

        collector = ObservationCoordinator(
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
        collector = ObservationCoordinator(
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

        class SlowCollector(FakeProjectCollector):
            @override
            def observe_issues(self) -> IssueSourceObservation:
                nonlocal active, maximum_active
                with counter_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.03)
                with counter_lock:
                    active -= 1
                return super().observe_issues()

        collector = ObservationCoordinator(
            [resolved_project()],
            factory=lambda _target, **_kwargs: SlowCollector(good_snapshot),
            agent_observer=lambda _targets: ([], []),
        )
        results: list[ProjectSnapshot] = []

        def refresh() -> None:
            results.append(snapshot_of(collector.refresh().projects[0]))

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
