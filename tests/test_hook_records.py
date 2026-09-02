from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from typing_extensions import override

from dashpot.agents import observe_agent_runs
from dashpot.hook_records import (
    HookRecordStore,
    now_iso,
    publish_hook_event,
    session_directory,
    write_hook_record,
)
from dashpot.model import ObservationTarget
from dashpot.processes import AgentAncestry, ProcessIdentity, SessionProcessRecord
from factories import hook_record_document, observation_target, write_config_marker
from helpers import present


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
        write_hook_record(
            hook_record_document(
                repository_root,
                session_id,
                "codex",
                process,
                state=state,
                at="2026-08-24T15:00:00Z",
                cwd=cwd,
                event="Stop" if state == "waiting" else "PreToolUse",
            ),
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

    def test_a_sandboxed_publication_records_why_the_host_is_unknown(self) -> None:
        # A hook that cannot see its own harness process records the reason,
        # so a sandboxed session is never mistaken for one with no harness.
        with mock.patch(
            "dashpot.hook_records.observe_agent_ancestry",
            return_value=AgentAncestry(None, "isolated-namespace"),
        ):
            publish_hook_event(
                {"session_id": "sandboxed", "cwd": "/repo", "hook_event_name": "Stop"},
                self.state_dir,
                environ={},
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
            environ={},
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
            environ={},
            process=self.process,
        )

        self.assertEqual(session_directory(self.worktree), written.parent)

    def test_publish_falls_back_to_the_global_store_when_unconfigured(
        self,
    ) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.worktree, check=True)

        with mock.patch(
            "dashpot.hook_records.state_directory", return_value=self.state_dir
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
            environ={},
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

    def test_a_new_session_starts_with_no_live_subagents(self) -> None:
        self.publish("UserPromptSubmit")
        self.publish("SubagentStart", "agent-1")

        self.publish("SessionStart")

        self.assertEqual([], self.stored()["liveSubagents"])
        self.publish("Stop")
        self.assertEqual("waiting", self.stored()["state"])

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
