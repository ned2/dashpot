from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast, override
from unittest import mock

import pytest

from dashpot.core.model import ObservationTarget
from dashpot.core.timestamps import utc_now, utc_stamp
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecordStore,
    build_hook_record,
    project_session_store,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import classify_hook_record
from dashpot.sessions.liveness import LivenessProbe
from dashpot.sessions.processes import (
    AgentAncestry,
    ProcessIdentity,
    ProcessLookup,
    SessionProcessRecord,
)
from dashpot.sessions.work import start_issue_work
from dashpot.sessions.work_store import WorkStore
from factories import (
    CLAUDE,
    CODEX,
    hook_record_document,
    observation_target,
    write_config_marker,
)
from helpers import absent, present
from test_work import (
    CLAUDE_ENVIRON,
    CLAUDE_SESSION,
    CODEX_SESSION,
    target,
    two_worktrees,
)


class HookRecordDegradationTests(unittest.TestCase):
    """Only fatal fields lose a record; the rest degrade with a diagnostic."""

    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    @override
    def tearDown(self) -> None:
        self.temporary.cleanup()

    def observe(self, **changes: object) -> tuple[list[Any], list[Any]]:
        record = hook_record_document(
            "/repo", "degraded", "codex", self.process, at="2026-08-24T15:00:00Z"
        )
        record.update(changes)
        (self.state_dir / "degraded.json").write_text(json.dumps(record))
        return observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

    def test_a_wrong_typed_optional_field_degrades_to_absent(self) -> None:
        runs, diagnostics = self.observe(branch=3, lastActivityAt=["not", "text"])

        self.assertEqual(1, len(runs))
        # The Observation Target's branch stands in for the unreadable one.
        self.assertEqual("main", runs[0].branch)
        self.assertIsNone(runs[0].last_activity_at)
        codes = [diagnostic.code for diagnostic in diagnostics]
        self.assertEqual(["agent-session-record-degraded"] * 2, codes)
        self.assertIn("branch", diagnostics[0].message)
        self.assertIn("lastActivityAt", diagnostics[1].message)

    def test_a_malformed_process_degrades_to_unknown_liveness(self) -> None:
        runs, diagnostics = self.observe(sessionProcess={"pid": "42"})

        self.assertEqual(1, len(runs))
        self.assertEqual("unknown", runs[0].state)
        self.assertIn(
            "agent-session-record-degraded",
            [diagnostic.code for diagnostic in diagnostics],
        )
        self.assertIn(
            "no recorded process identity",
            " ".join(diagnostic.message for diagnostic in diagnostics),
        )

    def test_a_fatal_field_loses_the_record(self) -> None:
        for changes, expected in (
            ({"cwd": ""}, "cwd"),
            ({"state": "sleeping"}, "unsupported active state"),
            ({"sessionId": "bad/id"}, "unsupported characters"),
            ({"harness": 3}, "harness"),
        ):
            with self.subTest(changes=changes):
                runs, diagnostics = self.observe(**changes)

                self.assertEqual([], runs)
                self.assertEqual(1, len(diagnostics))
                self.assertIn(expected, diagnostics[0].message)

    def test_a_missing_harness_is_read_as_codex(self) -> None:
        record = hook_record_document("/repo", "legacy", "codex", self.process)
        del record["harness"]
        (self.state_dir / "legacy.json").write_text(json.dumps(record))

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("codex", runs[0].harness)

    def test_a_retired_global_binding_is_detected_among_the_extras(self) -> None:
        runs, diagnostics = self.observe(issueId="I_legacy")

        self.assertEqual(1, len(runs))
        self.assertIsNone(runs[0].issue_id)
        self.assertEqual(
            ["agent-global-binding-rejected"],
            [diagnostic.code for diagnostic in diagnostics],
        )

    def test_the_process_record_omits_absent_arguments(self) -> None:
        bare = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")
        full = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026", "codex -q")

        self.assertNotIn("arguments", bare.as_record())
        self.assertEqual("codex -q", full.as_record()["arguments"])
        self.assertEqual(
            full, SessionProcessRecord.model_validate(full.as_record()).identity
        )


class HookRecordStoreTests(unittest.TestCase):
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
        HookRecordStore(self.state_dir).write(
            hook_record_document(
                repository_root,
                session_id,
                "codex",
                process,
                state=state,
                at="2026-08-24T15:00:00Z",
                cwd=cwd,
                event="Stop" if state == "waiting" else "PreToolUse",
            )
        )

    def test_the_freshest_record_wins_whatever_its_stamp_precision(self) -> None:
        # The same session is recorded globally and Project-locally around an
        # integration upgrade. A whole-second stamp is not an older one.
        worktree = Path(self.temporary.name) / "repo"
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
        HookRecordStore(self.state_dir).write(record)
        project_session_store(worktree).write(
            {**record, "lastActivityAt": "2026-08-24T15:00:00.500000Z"}
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

        HookRecordStore(self.state_dir).write(
            record("running", "2026-08-24T15:00:00.000000Z")
        )
        self.assertEqual("2026-08-24T15:00:00.000000Z", stored()["turnStartedAt"])

        # Later events in the same turn do not restart its clock.
        HookRecordStore(self.state_dir).write(
            record("running", "2026-08-24T15:04:00.000000Z")
        )
        self.assertEqual("2026-08-24T15:00:00.000000Z", stored()["turnStartedAt"])

        # The turn ends, and a waiting session has no turn in flight.
        HookRecordStore(self.state_dir).write(
            record("waiting", "2026-08-24T15:05:00.000000Z")
        )
        self.assertIsNone(stored()["turnStartedAt"])

        # The next turn starts its own clock.
        HookRecordStore(self.state_dir).write(
            record("running", "2026-08-24T15:09:00.000000Z")
        )
        self.assertEqual("2026-08-24T15:09:00.000000Z", stored()["turnStartedAt"])

    def test_stamps_are_fixed_width_so_records_order_by_text_too(self) -> None:
        self.assertRegex(utc_now(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")

    def test_graceful_session_end_removes_the_record(self) -> None:
        event = {"session_id": "graceful", "cwd": "/repo", "hook_event_name": "Stop"}
        publish_hook_event(event, self.state_dir, process=self.process)
        self.assertTrue((self.state_dir / "graceful.json").exists())

        publish_hook_event(
            {**event, "hook_event_name": "SessionEnd"},
            self.state_dir,
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

    def test_session_end_from_a_reparented_host_removes_the_record(self) -> None:
        # A Codex daemon a terminal autostarted is reparented when that
        # terminal exits; its pid and start time still name the same Host
        # Process, since neither its parent nor its arguments is identity
        # (measured on 0.159.3, #161).
        launched = ProcessIdentity(
            42, 4100, "codex", "Tue Aug 25 01:00:00 2026", "app-server --listen"
        )
        reparented = ProcessIdentity(
            42, 1, "codex", "Tue Aug 25 01:00:00 2026", "app-server --managed-daemon"
        )
        event = {"session_id": "unloaded", "cwd": "/repo", "hook_event_name": "Stop"}
        publish_hook_event(event, self.state_dir, process=launched)

        publish_hook_event(
            {**event, "hook_event_name": "SessionEnd"},
            self.state_dir,
            process=reparented,
        )

        self.assertFalse((self.state_dir / "unloaded.json").exists())

    def test_session_end_from_a_reused_pid_keeps_the_record(self) -> None:
        event = {"session_id": "reused", "cwd": "/repo", "hook_event_name": "Stop"}
        publish_hook_event(event, self.state_dir, process=self.process)

        publish_hook_event(
            {**event, "hook_event_name": "SessionEnd"},
            self.state_dir,
            process=ProcessIdentity(42, 1, "codex", "Wed Aug 26 01:00:00 2026"),
        )

        self.assertEqual(
            "waiting",
            json.loads((self.state_dir / "reused.json").read_text())["state"],
        )

    def test_session_end_matches_an_unreadable_process_only_as_recorded(
        self,
    ) -> None:
        # A process record that cannot be read has no pid and start time to
        # compare, so only the identical record names the same Host Process.
        unreadable = {"pid": "unreadable", "command": "codex"}
        readable = self.process.as_record()
        for previous, ending, removed in (
            (unreadable, unreadable, True),
            (unreadable, {**unreadable, "command": "other"}, False),
            (unreadable, readable, False),
            (readable, unreadable, False),
        ):
            with self.subTest(previous=previous, ending=ending):
                base = {
                    "version": 2,
                    "sessionId": "opaque",
                    "harness": "codex",
                    "lastActivityAt": "2026-08-25T16:00:00Z",
                }
                HookRecordStore(self.state_dir).write(
                    {**base, "sessionProcess": previous, "state": "waiting"}
                )

                HookRecordStore(self.state_dir).write(
                    {**base, "sessionProcess": ending, "state": "ended"}
                )

                self.assertEqual(not removed, (self.state_dir / "opaque.json").exists())

    def test_session_end_with_a_malformed_binding_still_removes_the_record(
        self,
    ) -> None:
        self.write("ending", "waiting", self.process)

        HookRecordStore(self.state_dir).write(
            {
                "version": 2,
                "sessionId": "ending",
                "harness": "codex",
                "sessionProcess": self.process.as_record(),
                "lastActivityAt": "2026-08-25T16:00:00Z",
                "state": "ended",
                "issueId": "not an id",
            }
        )

        self.assertFalse((self.state_dir / "ending.json").exists())

    def test_prune_lock_keeps_the_lock_of_an_existing_record(self) -> None:
        self.write("live", "running", self.process)
        store = HookRecordStore(self.state_dir)

        self.assertFalse(store.prune_lock("live"))
        self.assertTrue((self.state_dir / ".live.lock").exists())

        (self.state_dir / "live.json").unlink()
        self.assertIn("live", store.orphaned_locks())
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

    def test_prune_keeps_a_record_it_can_no_longer_read(self) -> None:
        # A record rewritten as something other than an object since it was
        # observed is not the observed one, and only that one may go.
        self.write("stale", "running", self.process)
        path = self.state_dir / "stale.json"
        observed = json.loads(path.read_text())
        store = HookRecordStore(self.state_dir)

        path.write_text("[]")
        self.assertFalse(store.prune("stale", observed))
        path.write_text("{")
        self.assertFalse(store.prune("stale", observed))
        self.assertTrue(path.exists())

    def test_malformed_record_becomes_diagnostic(self) -> None:
        (self.state_dir / "bad.json").write_text(json.dumps({"version": 99}))

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]}, self.state_dir
        )

        self.assertEqual([], runs)
        self.assertIn("unsupported record", diagnostics[0].message)

    def test_unsupported_harness_record_becomes_a_diagnostic(self) -> None:
        HookRecordStore(self.state_dir).write(
            {
                "version": 2,
                "sessionId": "mystery",
                "harness": "cursor",
                "state": "running",
                "cwd": "/repo",
                "repositoryRoot": "/repo",
                "event": "UserPromptSubmit",
                "sessionProcess": None,
            }
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

    def test_a_sandboxed_publication_records_why_the_host_is_unknown(self) -> None:
        # A hook that cannot see its own harness process records the reason,
        # so a sandboxed session is never mistaken for one with no harness.
        with mock.patch(
            "dashpot.sessions.hook_publish.observe_agent_ancestry",
            return_value=AgentAncestry(None, "isolated-namespace"),
        ):
            publish_hook_event(
                {"session_id": "sandboxed", "cwd": "/repo", "hook_event_name": "Stop"},
                self.state_dir,
            )

        record = json.loads((self.state_dir / "sandboxed.json").read_text())
        self.assertIsNone(record["sessionProcess"])
        self.assertEqual("isolated-namespace", record["sessionProcessUnobservable"])

    def test_interrupt_event_publishes_a_waiting_record(self) -> None:
        publish_hook_event(
            {
                "session_id": "interrupted",
                "cwd": "/repo",
                "hook_event_name": "Interrupt",
            },
            self.state_dir,
            process=self.process,
        )

        record = json.loads((self.state_dir / "interrupted.json").read_text())
        self.assertEqual("waiting", record["state"])


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
        return hook_record_document(
            self.worktree,
            "routed",
            "codex",
            self.process,
            state=state,
            at=last_activity_at,
            event="Stop" if state == "waiting" else "PreToolUse",
        )

    def targets(self) -> dict[str, list[ObservationTarget]]:
        return {"project:example": [observation_target(str(self.worktree))]}

    def test_publish_routes_to_a_configured_projects_local_store(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.worktree, check=True)
        write_config_marker(self.worktree)

        written = publish_hook_event(
            {
                "session_id": "routed",
                "cwd": str(self.worktree),
                "hook_event_name": "Stop",
            },
            process=self.process,
        )

        self.assertEqual(session_directory(self.worktree), written.path.parent)

    def test_publish_falls_back_to_the_global_store_when_unconfigured(
        self,
    ) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.worktree, check=True)

        with mock.patch(
            "dashpot.sessions.hook_publish.state_directory", return_value=self.state_dir
        ):
            written = publish_hook_event(
                {
                    "session_id": "routed",
                    "cwd": str(self.worktree),
                    "hook_event_name": "Stop",
                },
                process=self.process,
            )

        self.assertEqual(self.state_dir, written.path.parent)
        self.assertFalse((self.worktree / ".dashpot").exists())

    def test_project_local_records_are_observed(self) -> None:
        project_session_store(self.worktree).write(
            self.record("waiting", "2026-08-24T15:00:00Z")
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
        HookRecordStore(self.state_dir).write(
            self.record("running", "2026-08-24T14:00:00Z")
        )
        project_session_store(self.worktree).write(
            self.record("waiting", "2026-08-24T15:00:00Z")
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


class SubagentBoundaryTests(unittest.TestCase):
    """A session stays running while a sub-agent it delegated to is alive."""

    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.process = ProcessIdentity(42, 1, "claude", "Tue Aug 25 01:00:00 2026")

    @override
    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish(self, event_name: str, agent_id: str | None = None) -> None:
        event: dict[str, Any] = {
            "session_id": "delegating",
            "cwd": "/repo",
            "hook_event_name": event_name,
        }
        if agent_id is not None:
            event["agent_id"] = agent_id
        publish_hook_event(
            event,
            self.state_dir,
            process=self.process,
            harness="claude-code",
        )

    def stored(self) -> dict[str, Any]:
        path = self.state_dir / "delegating.json"
        return cast("dict[str, Any]", json.loads(path.read_text()))

    def test_a_stop_with_a_background_subagent_alive_keeps_the_session_running(
        self,
    ) -> None:
        self.publish("UserPromptSubmit")
        turn_started = self.stored()["turnStartedAt"]
        self.publish("SubagentStart", "agent-1")
        self.assertEqual("running", self.stored()["state"])
        self.assertEqual(["agent-1"], self.stored()["liveSubagents"])
        # A sub-agent's boundary is not the main turn's.
        self.assertEqual(turn_started, self.stored()["turnStartedAt"])

        self.publish("Stop")

        record = self.stored()
        self.assertEqual("running", record["state"])
        self.assertEqual("Stop", record["event"])
        self.assertIsNone(record["turnStartedAt"])

        self.publish("SubagentStop", "agent-1")

        record = self.stored()
        self.assertEqual("waiting", record["state"])
        self.assertEqual([], record["liveSubagents"])

        # The next main turn starts its own clock.
        self.publish("UserPromptSubmit")
        record = self.stored()
        self.assertEqual("running", record["state"])
        self.assertEqual(record["lastActivityAt"], record["turnStartedAt"])

    def test_a_foreground_subagent_stopping_leaves_the_main_turn_running(
        self,
    ) -> None:
        self.publish("UserPromptSubmit")
        turn_started = self.stored()["turnStartedAt"]
        self.publish("SubagentStart", "agent-1")
        self.publish("SubagentStop", "agent-1")

        record = self.stored()
        self.assertEqual("running", record["state"])
        self.assertEqual(turn_started, record["turnStartedAt"])
        self.assertEqual([], record["liveSubagents"])

    def test_the_last_live_subagent_ends_the_delegated_work(self) -> None:
        self.publish("UserPromptSubmit")
        self.publish("SubagentStart", "agent-1")
        self.publish("SubagentStart", "agent-2")
        self.publish("Stop")
        self.publish("SubagentStop", "agent-1")

        self.assertEqual("running", self.stored()["state"])
        self.assertEqual(["agent-2"], self.stored()["liveSubagents"])

        self.publish("SubagentStop", "agent-2")

        self.assertEqual("waiting", self.stored()["state"])

    def test_a_start_of_the_same_process_keeps_its_live_subagents(self) -> None:
        # Claude Code compacts a live session with a SessionStart and no
        # SessionEnd, while its sub-agents keep working (ADR 0097).
        self.publish("UserPromptSubmit")
        self.publish("SubagentStart", "agent-1")

        self.publish("SessionStart")

        self.assertEqual(["agent-1"], self.stored()["liveSubagents"])
        self.publish("Stop")
        self.assertEqual("running", self.stored()["state"])

    def test_a_start_of_another_process_starts_with_no_live_subagents(self) -> None:
        self.publish("UserPromptSubmit")
        self.publish("SubagentStart", "agent-1")
        self.process = ProcessIdentity(43, 1, "claude", "Tue Aug 25 02:00:00 2026")

        self.publish("SessionStart")

        self.assertEqual([], self.stored()["liveSubagents"])
        self.publish("Stop")
        self.assertEqual("waiting", self.stored()["state"])

    def test_a_start_naming_no_process_starts_with_no_live_subagents(self) -> None:
        # Nothing shows that an unnamed process is the one that started them.
        store = HookRecordStore(self.state_dir)
        for event_name, agent_id in (
            ("UserPromptSubmit", None),
            ("SubagentStart", "agent-1"),
            ("SessionStart", None),
        ):
            event: dict[str, Any] = {
                "session_id": "delegating",
                "cwd": "/repo",
                "hook_event_name": event_name,
            }
            if agent_id is not None:
                event["agent_id"] = agent_id
            store.write(
                build_hook_record(
                    event, harness="claude-code", process_unobservable="sandboxed"
                )
            )

        self.assertEqual([], self.stored()["liveSubagents"])

    def test_a_subagent_event_naming_no_agent_changes_nothing(self) -> None:
        self.publish("UserPromptSubmit")
        self.publish("SubagentStart")
        self.assertEqual([], self.stored()["liveSubagents"])

        self.publish("Stop")

        self.assertEqual("waiting", self.stored()["state"])

    def test_the_observed_run_is_running_while_a_subagent_works(self) -> None:
        self.publish("UserPromptSubmit")
        self.publish("SubagentStart", "agent-1")
        self.publish("Stop")

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual("running", runs[0].state)

    def test_malformed_live_subagents_degrade_to_none(self) -> None:
        record = hook_record_document(
            "/repo", "delegating", "claude-code", self.process, state="waiting"
        )
        record["liveSubagents"] = "agent-1"
        (self.state_dir / "delegating.json").write_text(json.dumps(record))

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual("waiting", runs[0].state)
        self.assertEqual(
            ["agent-session-record-degraded"], [d.code for d in diagnostics]
        )

    def test_a_sub_agents_own_events_keep_the_parents_turn(self) -> None:
        self.publish("UserPromptSubmit")
        self.publish("Stop")

        # A sub-agent's prompt and tool calls are not its parent's turn.
        self.publish("UserPromptSubmit", "agent-1")
        self.publish("PostToolUse", "agent-1")

        record = self.stored()
        self.assertEqual("waiting", record["state"])
        self.assertIsNone(record["turnStartedAt"])
        self.assertEqual([], record["liveSubagents"])

    def test_a_late_stop_after_the_session_ended_invents_no_session(self) -> None:
        # Measured on Codex: a child's boundary can follow its root's
        # SessionEnd, and a record written then would list the ended session
        # as waiting while a shared Host Process lives. The rule is shared,
        # so Claude Code takes it too.
        for harness, process in (("codex", CODEX), ("claude-code", self.process)):
            with self.subTest(harness=harness):
                for event_name, agent_id in (
                    ("UserPromptSubmit", None),
                    ("SubagentStart", "agent-1"),
                    ("Stop", None),
                    ("SessionEnd", None),
                    ("SubagentStop", "agent-1"),
                ):
                    event: dict[str, Any] = {
                        "session_id": f"ended-{harness}",
                        "cwd": "/repo",
                        "hook_event_name": event_name,
                    }
                    if agent_id is not None:
                        event["agent_id"] = agent_id
                    publish_hook_event(
                        event,
                        self.state_dir,
                        process=process,
                        harness=cast("Any", harness),
                    )

                self.assertEqual([], list(self.state_dir.glob("*.json")))
                runs, _diagnostics = observe_agent_runs(
                    {"project:example": [observation_target()]},
                    self.state_dir,
                    lookup=present(process),
                )
                self.assertEqual([], runs)


class SessionStartStampTests(unittest.TestCase):
    """A store remembers when it last saw its session begin an incarnation."""

    @override
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")

    @override
    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish(self, event_name: str, **fields: object) -> dict[str, Any]:
        publish_hook_event(
            {
                "session_id": "restarting",
                "cwd": "/repo",
                "hook_event_name": event_name,
                **fields,
            },
            self.state_dir,
            process=self.process,
            harness="codex",
        )
        path = self.state_dir / "restarting.json"
        return cast("dict[str, Any]", json.loads(path.read_text()))

    def test_session_start_sets_the_stamp_and_later_events_carry_it(self) -> None:
        started = self.publish("SessionStart")
        self.assertEqual(started["lastActivityAt"], started["lastSessionStartAt"])
        self.assertEqual(2, started["version"])

        later = self.publish("UserPromptSubmit")

        self.assertEqual(started["lastSessionStartAt"], later["lastSessionStartAt"])
        self.assertNotEqual(later["lastActivityAt"], later["lastSessionStartAt"])

    def test_a_store_that_saw_no_session_start_writes_no_stamp(self) -> None:
        self.assertNotIn("lastSessionStartAt", self.publish("UserPromptSubmit"))

    def test_a_sub_agents_session_start_is_not_its_parents(self) -> None:
        self.publish("UserPromptSubmit")

        self.assertNotIn(
            "lastSessionStartAt", self.publish("SessionStart", agent_id="child")
        )

    def test_a_record_written_before_the_stamp_existed_stays_readable(self) -> None:
        legacy = hook_record_document(
            "/repo", "restarting", "codex", self.process, at="2026-08-24T15:00:00Z"
        )
        (self.state_dir / "restarting.json").write_text(json.dumps(legacy))

        runs, diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], diagnostics)
        self.assertEqual(["running"], [run.state for run in runs])
        self.assertNotIn("lastSessionStartAt", self.publish("Stop"))


def test_a_late_stop_reaches_its_parents_record_in_another_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child's stop with no record at its own cwd still finds its parent's."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))
    a, b = two_worktrees(tmp_path)

    def publish(at: Path, event_name: str, agent_id: str | None = None) -> Path:
        event: dict[str, Any] = {
            "session_id": CODEX_SESSION,
            "cwd": str(at),
            "hook_event_name": event_name,
        }
        if agent_id is not None:
            event["agent_id"] = agent_id
        return publish_hook_event(
            event, process=CODEX, harness="codex", lookup=present(CODEX)
        ).path

    publish(b, "UserPromptSubmit")
    publish(b, "SubagentStart", "agent-1")
    publish(b, "Stop")

    written = publish(a, "SubagentStop", "agent-1")

    assert written.parent == session_directory(b)
    assert not session_directory(a).exists() or not list(
        session_directory(a).glob("*.json")
    )
    parent = json.loads(written.read_text())
    assert (parent["state"], parent["liveSubagents"], parent["cwd"]) == (
        "waiting",
        [],
        str(b),
    )


@dataclass(frozen=True, slots=True)
class SubAgentParent:
    """How a harness binds a session at a Worktree and moves it live."""

    session: str
    process: ProcessIdentity
    environ: dict[str, str]
    # The designated location evidence arriving at a Worktree (ADR 0067,
    # ADR 0074).
    moving: dict[str, Any]


SUB_AGENT_HARNESSES = {
    "codex": SubAgentParent(
        CODEX_SESSION,
        CODEX,
        {"CODEX_THREAD_ID": CODEX_SESSION},
        {"hook_event_name": "UserPromptSubmit"},
    ),
    "claude-code": SubAgentParent(
        CLAUDE_SESSION,
        CLAUDE,
        CLAUDE_ENVIRON,
        {"hook_event_name": "PostToolUse", "tool_name": "EnterWorktree"},
    ),
}


@pytest.mark.parametrize("harness", SUB_AGENT_HARNESSES)
def test_a_sub_agent_event_stamped_before_a_move_never_rewinds_its_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harness: str
) -> None:
    """A child's event written after its parent moved keeps the parent's stamp."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))
    parent = SUB_AGENT_HARNESSES[harness]
    a, b = two_worktrees(tmp_path)

    def publish(at: Path, fields: dict[str, Any], stamp: str | None = None) -> str:
        """Publish one event, its hook's clock reading ``stamp`` when given."""
        clock = (
            nullcontext()
            if stamp is None
            else mock.patch("dashpot.sessions.hook_records.utc_now", return_value=stamp)
        )
        with clock:
            publication = publish_hook_event(
                {"session_id": parent.session, "cwd": str(at), **fields},
                process=parent.process,
                harness=cast("Any", harness),
                lookup=present(parent.process),
            )
        return publication.work

    def stamp_of(at: Path) -> str:
        document = json.loads(
            (session_directory(at) / f"{parent.session}.json").read_text()
        )
        return cast("str", document["lastActivityAt"])

    publish(a, {"hook_event_name": "UserPromptSubmit"})
    start_issue_work(
        a, "build-observer", lookup=present(parent.process), environ=parent.environ
    )
    left_at = datetime.fromisoformat(stamp_of(a).replace("Z", "+00:00"))
    assert publish(b, parent.moving) == "relocated"
    moved_at = stamp_of(b)

    # Stamped after the record at A but before the move, written after it.
    publish(
        b,
        {"hook_event_name": "PostToolUse", "tool_name": "Bash", "agent_id": "late"},
        stamp=utc_stamp(left_at + timedelta(microseconds=1)),
    )

    assert stamp_of(b) == moved_at
    runs, diagnostics = observe_agent_runs(
        {"project:test": [target(a), target(b)]},
        state_directory(),
        lookup=present(parent.process),
    )
    assert [(run.observation_target, run.issue_id) for run in runs] == [
        (str(b), "I_observer")
    ]
    assert diagnostics == []

    # A designated event at A, stamped before the move too, carries nothing.
    stale = publish(
        a, parent.moving, stamp=utc_stamp(left_at + timedelta(microseconds=2))
    )

    assert stale == "unchanged"
    assert WorkStore(a).active()[0] == []
    assert [item.issue_id for item in WorkStore(b).active()[0]] == ["I_observer"]


# A record that names its Host Process and also says nothing observes the
# session there: what a retired OpenCode generation leaves (ADR 0080).
UNOBSERVED_OPENCODE = ProcessIdentity(4100, 1, "opencode", "Tue Aug 25 03:00:00 2026")


def classified(
    harness: str,
    process: ProcessIdentity | None,
    unobservable: str | None,
    lookup: ProcessLookup,
    state: str = "waiting",
) -> tuple[str, str | None]:
    raw = hook_record_document("/repo", "classified", harness, process, state=state)
    raw["sessionProcessUnobservable"] = unobservable
    record = classify_hook_record(raw, LivenessProbe(lookup))
    return record.outcome, record.reason


def test_an_unobserved_record_reads_unknown_while_its_process_lives() -> None:
    assert classified(
        "opencode",
        UNOBSERVED_OPENCODE,
        "opencode-no-live-instance",
        present(UNOBSERVED_OPENCODE),
    ) == ("unknown", "opencode-no-live-instance")


def test_an_unobserved_record_reads_gone_once_its_process_is_gone() -> None:
    assert classified(
        "opencode", UNOBSERVED_OPENCODE, "opencode-no-live-instance", absent()
    ) == ("gone", None)


@pytest.mark.parametrize(
    ("harness", "process"), [("codex", CODEX), ("claude-code", CLAUDE)]
)
def test_a_record_with_one_of_process_and_unobservable_classifies_as_before(
    harness: str, process: ProcessIdentity
) -> None:
    assert classified(harness, process, None, present(process)) == ("live", None)
    assert classified(harness, process, None, absent()) == ("gone", None)
    assert classified(harness, None, "isolated-namespace", present(process)) == (
        "unknown",
        "no recorded process identity",
    )
    assert classified(harness, None, "isolated-namespace", absent()) == (
        "unknown",
        "no recorded process identity",
    )


def test_an_ended_unobserved_record_stays_ended() -> None:
    assert classified(
        "opencode",
        UNOBSERVED_OPENCODE,
        "opencode-no-live-instance",
        present(UNOBSERVED_OPENCODE),
        state="ended",
    ) == ("ended", None)


# What Claude Code 2.1.289 published under #448, with what Dashpot's publisher
# received recorded in order (docs/spikes/session-start-on-a-live-session-spike.md).
CLAUDE_448_TRACE = (
    Path(__file__).resolve().parents[1]
    / "docs/spikes/measurements/issue-448-claude-trace.jsonl"
)


@dataclass(frozen=True, slots=True)
class MeasuredHook:
    """One hook event Dashpot's publisher received in a #448 scenario."""

    receipt: int
    payload: dict[str, Any]
    # The Host Process the publisher identified, as the stored record names it.
    host: ProcessIdentity

    @property
    def agent(self) -> str | None:
        """The Sub-agent whose event this is, if it is one's."""
        return cast("str | None", self.payload.get("agent_id"))


def measured_hooks(scenario: str) -> list[MeasuredHook]:
    """The events a #448 Claude Code scenario delivered to Dashpot, in order.

    ``PreCompact`` and ``PostCompact`` were observed only: no Dashpot
    integration subscribes them, so the publisher never received them.
    """
    hooks: list[MeasuredHook] = []
    current: str | None = None
    # The start each stored record names for its process; the SessionEnd that
    # removes the last record names none, so a host keeps its first start.
    starts: dict[int, str] = {}
    for line in CLAUDE_448_TRACE.read_text().splitlines():
        entry = json.loads(line)
        if entry["kind"] == "scenario":
            current = cast("str", entry["name"])
        elif (
            entry["kind"] == "hook" and current == scenario and not entry["observeOnly"]
        ):
            for record in entry["store"]:
                starts.setdefault(record["processPid"], record["processStartedAt"])
            pid = cast("int", entry["hostPid"])
            host = ProcessIdentity(pid, 1, "claude", starts[pid])
            hooks.append(MeasuredHook(entry["receipt"], entry["payload"], host))
    assert hooks, f"no hooks recorded for scenario {scenario!r}"
    return hooks


def worker_agents(hooks: list[MeasuredHook]) -> set[str]:
    """The scenario's started Sub-agents; a compaction's summarizer never starts."""
    return {
        hook.agent
        for hook in hooks
        if hook.payload["hook_event_name"] == "SubagentStart" and hook.agent
    }


def replay(
    hooks: list[MeasuredHook], directory: Path, *, without: set[str] | None = None
) -> dict[int, dict[str, Any]]:
    """Publish a measured order and return the session's record after each receipt.

    A receipt after which the session has no record, its ``SessionEnd``'s, is
    absent. ``without`` drops those Sub-agents' events, as though the session had
    delegated to none of them.
    """
    stored: dict[int, dict[str, Any]] = {}
    for hook in hooks:
        if without and hook.agent in without:
            continue
        written = publish_hook_event(
            {**hook.payload, "cwd": "/repo"},
            directory,
            process=hook.host,
            harness="claude-code",
        ).path
        # The session's SessionEnd at the scenario's close removes its record.
        if written.exists():
            stored[hook.receipt] = json.loads(written.read_text())
    return stored


# Each measured `/compact`: its compaction's SessionStart and its worker's stop.
MANUAL_COMPACTIONS = {"compact": (19, 32), "headless-compact": (316, 336)}


@pytest.mark.parametrize("scenario", MANUAL_COMPACTIONS)
def test_a_measured_manual_compaction_keeps_the_session_waiting_once_its_worker_stops(
    tmp_path: Path, scenario: str
) -> None:
    # `/compact` publishes no prompt and no Stop (ADR 0100); the worker the
    # session left working holds it running until its own stop (ADR 0016).
    compaction, worker_stop = MANUAL_COMPACTIONS[scenario]
    hooks = measured_hooks(scenario)
    (worker,) = worker_agents(hooks)

    stored = replay(hooks, tmp_path)

    compacted = stored[compaction]
    assert (compacted["source"], compacted["state"]) == ("compact", "running")
    assert compacted["liveSubagents"] == [worker]
    assert compacted["turnStartedAt"] is None
    assert (stored[worker_stop]["state"], stored[worker_stop]["liveSubagents"]) == (
        "waiting",
        [],
    )


@pytest.mark.parametrize("scenario", MANUAL_COMPACTIONS)
def test_a_measured_manual_compaction_of_a_waiting_session_reads_waiting(
    tmp_path: Path, scenario: str
) -> None:
    compaction, _worker_stop = MANUAL_COMPACTIONS[scenario]
    hooks = measured_hooks(scenario)

    # Observed before the session's next prompt.
    until_compaction = [hook for hook in hooks if hook.receipt <= compaction]

    stored = replay(until_compaction, tmp_path, without=worker_agents(hooks))

    assert stored[compaction]["state"] == "waiting"
    assert stored[compaction]["turnStartedAt"] is None
    runs, diagnostics = observe_agent_runs(
        {"project:example": [observation_target()]},
        tmp_path,
        lookup=present(hooks[0].host),
    )
    assert diagnostics == []
    assert [run.state for run in runs] == ["waiting"]


# The measured `auto-compact`: its compaction's SessionStart, the turn's Stop
# that follows it, and its worker's stop.
AUTO_COMPACTION, AUTO_COMPACTED_STOP, AUTO_WORKER_STOP = 115, 119, 131


def test_a_measured_auto_compaction_runs_until_its_turn_stops(tmp_path: Path) -> None:
    # Automatic compaction runs inside a turn, whose Stop follows it.
    hooks = measured_hooks("auto-compact")
    (worker,) = worker_agents(hooks)
    prompt = next(
        hook.receipt
        for hook in hooks
        if hook.payload["hook_event_name"] == "UserPromptSubmit"
    )

    stored = replay(hooks, tmp_path)

    compacted = stored[AUTO_COMPACTION]
    assert (compacted["source"], compacted["state"]) == ("compact", "running")
    assert compacted["turnStartedAt"] == stored[prompt]["turnStartedAt"]
    assert compacted["liveSubagents"] == [worker]
    # The turn's Stop leaves the worker holding the session running.
    stopped = stored[AUTO_COMPACTED_STOP]
    assert (stopped["state"], stopped["turnStartedAt"]) == ("running", None)
    assert stored[AUTO_WORKER_STOP]["state"] == "waiting"

    alone = replay(hooks, tmp_path / "alone", without={worker})

    assert alone[AUTO_COMPACTION]["state"] == "running"
    assert alone[AUTO_COMPACTED_STOP]["state"] == "waiting"


def claude_event(
    event_name: str, process: ProcessIdentity | None = CLAUDE, **fields: str
) -> dict[str, Any]:
    """The record a Claude Code hook event of the session ``compacting`` builds."""
    return build_hook_record(
        {
            "session_id": "compacting",
            "cwd": "/repo",
            "hook_event_name": event_name,
            **fields,
        },
        process=process,
        harness="claude-code",
        process_unobservable=None if process else "sandboxed",
    )


@pytest.mark.parametrize(
    ("process", "source"),
    [
        pytest.param(
            ProcessIdentity(7778, 1, "claude", "Tue Aug 25 03:00:00 2026"),
            "compact",
            id="another-process",
        ),
        pytest.param(None, "compact", id="no-process"),
        pytest.param(CLAUDE, "startup", id="another-source"),
        pytest.param(CLAUDE, None, id="no-source"),
    ],
)
def test_only_a_compaction_of_the_same_process_keeps_the_session_waiting(
    tmp_path: Path, process: ProcessIdentity | None, source: str | None
) -> None:
    store = HookRecordStore(tmp_path)
    store.write(claude_event("UserPromptSubmit"))
    store.write(claude_event("Stop"))
    fields = {} if source is None else {"source": source}

    store.write(claude_event("SessionStart", process, **fields))

    record = json.loads((tmp_path / "compacting.json").read_text())
    assert (record["state"], record["turnStartedAt"]) == (
        "running",
        record["lastActivityAt"],
    )


def test_a_compaction_after_an_ended_record_begins_the_session_running(
    tmp_path: Path,
) -> None:
    # The ended record kept for its sub-agent is no turn to go on with.
    store = HookRecordStore(tmp_path)
    store.write(claude_event("UserPromptSubmit"))
    store.write(claude_event("SubagentStart", agent_id="agent-1"))
    store.write(claude_event("Stop"))
    store.write(claude_event("SessionEnd"))

    store.write(claude_event("SessionStart", source="compact"))

    record = json.loads((tmp_path / "compacting.json").read_text())
    assert (record["state"], record["liveSubagents"]) == ("running", ["agent-1"])
    assert record["turnStartedAt"] == record["lastActivityAt"]


def test_a_compaction_takes_its_state_from_the_sessions_fresher_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A shell `cd` moves a Claude Code session's hooks with no hook of its own:
    # the record left at `a` still reads its old turn when the session, now
    # waiting at `b`, compacts back at `a` (ADR 0097).
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))
    a, b = two_worktrees(tmp_path)

    def publish(at: Path, event_name: str, **fields: str) -> dict[str, Any]:
        written = publish_hook_event(
            {
                "session_id": CLAUDE_SESSION,
                "cwd": str(at),
                "hook_event_name": event_name,
                **fields,
            },
            process=CLAUDE,
            harness="claude-code",
            lookup=present(CLAUDE),
        ).path
        return cast("dict[str, Any]", json.loads(written.read_text()))

    publish(a, "UserPromptSubmit")
    publish(b, "UserPromptSubmit")
    publish(b, "Stop")

    compacted = publish(a, "SessionStart", source="compact")

    assert (compacted["cwd"], compacted["state"]) == (str(a), "waiting")
    assert compacted["turnStartedAt"] is None


def test_a_compaction_after_an_ended_record_keeps_a_fresher_records_turn(
    tmp_path: Path,
) -> None:
    # The ended record here kept its sub-agent (ADR 0095); the session's
    # fresher live record of the same Host Process, elsewhere, is waiting.
    here = HookRecordStore(tmp_path / "here")
    here.write(claude_event("UserPromptSubmit"))
    here.write(claude_event("SubagentStart", agent_id="agent-1"))
    here.write(claude_event("SessionEnd"))
    elsewhere = HookRecordStore(tmp_path / "elsewhere")
    elsewhere.write(claude_event("UserPromptSubmit"))
    fresher = json.loads(elsewhere.write(claude_event("Stop")).read_text())

    written = here.write(claude_event("SessionStart", source="compact"), seed=fresher)

    record = json.loads(written.read_text())
    # Waiting, as the fresher record is; the kept sub-agent holds it running.
    assert (record["state"], record["liveSubagents"]) == ("running", ["agent-1"])
    assert record["turnStartedAt"] is None


def codex_event(event_name: str, **fields: str) -> dict[str, Any]:
    """The record a Codex hook event of the session ``compacting`` builds."""
    return build_hook_record(
        {
            "session_id": "compacting",
            "cwd": "/repo",
            "hook_event_name": event_name,
            **fields,
        },
        process=CODEX,
        harness="codex",
    )


def test_a_codex_manual_compaction_waits_for_the_prompt_that_follows_it(
    tmp_path: Path,
) -> None:
    # Codex 0.160.0 publishes a manual compaction's SessionStart at the next
    # turn's start, just before its UserPromptSubmit (#448, `compact`).
    store = HookRecordStore(tmp_path)
    store.write(codex_event("UserPromptSubmit"))
    store.write(codex_event("Stop"))

    compacted = json.loads(
        store.write(codex_event("SessionStart", source="compact")).read_text()
    )
    prompted = json.loads(store.write(codex_event("UserPromptSubmit")).read_text())

    assert (compacted["state"], compacted["turnStartedAt"]) == ("waiting", None)
    assert (prompted["state"], prompted["turnStartedAt"]) == (
        "running",
        prompted["lastActivityAt"],
    )


def test_a_codex_automatic_compaction_keeps_its_turn_until_it_stops(
    tmp_path: Path,
) -> None:
    # Codex 0.160.0 publishes an automatic compaction's SessionStart inside
    # the turn, whose Stop follows (#448, `auto-compact`).
    store = HookRecordStore(tmp_path)
    turn = json.loads(store.write(codex_event("UserPromptSubmit")).read_text())

    compacted = json.loads(
        store.write(codex_event("SessionStart", source="compact")).read_text()
    )
    stopped = json.loads(store.write(codex_event("Stop")).read_text())

    assert (compacted["state"], compacted["turnStartedAt"]) == (
        "running",
        turn["turnStartedAt"],
    )
    assert stopped["state"] == "waiting"
