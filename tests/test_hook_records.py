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

from dashpot.core.model import Harness, ObservationTarget
from dashpot.core.timestamps import utc_now, utc_stamp
from dashpot.sessions.agent_runs import observe_agent_runs
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecord,
    HookRecordStore,
    build_hook_record,
    project_session_store,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import (
    classify_hook_record,
    sessions_with_live_subagents,
)
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
            HookRecord.model_validate(
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
        HookRecordStore(self.state_dir).write(HookRecord.model_validate(record))
        project_session_store(worktree).write(
            HookRecord.model_validate(
                {**record, "lastActivityAt": "2026-08-24T15:00:00.500000Z"}
            )
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
            HookRecord.model_validate(record("running", "2026-08-24T15:00:00.000000Z"))
        )
        self.assertEqual("2026-08-24T15:00:00.000000Z", stored()["turnStartedAt"])

        # Later events in the same turn do not restart its clock.
        HookRecordStore(self.state_dir).write(
            HookRecord.model_validate(record("running", "2026-08-24T15:04:00.000000Z"))
        )
        self.assertEqual("2026-08-24T15:00:00.000000Z", stored()["turnStartedAt"])

        # The turn ends, and a waiting session has no turn in flight.
        HookRecordStore(self.state_dir).write(
            HookRecord.model_validate(record("waiting", "2026-08-24T15:05:00.000000Z"))
        )
        self.assertIsNone(stored()["turnStartedAt"])

        # The next turn starts its own clock.
        HookRecordStore(self.state_dir).write(
            HookRecord.model_validate(record("running", "2026-08-24T15:09:00.000000Z"))
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

    def test_session_end_reads_an_unreadable_process_as_naming_none(
        self,
    ) -> None:
        # The store reads the previous record as a scan reads it: a process
        # record that cannot be read degrades to naming no Host Process, which
        # is no evidence of another process (ADR 0132), so the newer end ends
        # the session whatever process it names.
        unreadable = {"pid": "unreadable", "command": "codex"}
        for ending in (self.process, None):
            with self.subTest(ending=ending):
                stored = {
                    **hook_record_document("/repo", "opaque", "codex", state="waiting"),
                    "sessionProcess": unreadable,
                }
                (self.state_dir / "opaque.json").write_text(json.dumps(stored))

                HookRecordStore(self.state_dir).write(
                    HookRecord.model_validate(
                        hook_record_document(
                            "/repo",
                            "opaque",
                            "codex",
                            ending,
                            state="ended",
                            at="2026-09-01T00:00:00Z",
                        )
                    )
                )

                self.assertFalse((self.state_dir / "opaque.json").exists())

    def test_a_session_end_beside_a_record_naming_no_process_ends_the_session(
        self,
    ) -> None:
        # A hook whose ancestry probe failed names no Host Process, only why
        # (#543). That is no evidence of another process, so the newer end
        # ends the session on either side of it.
        unnamed: dict[str, Any] = {
            "sessionProcess": None,
            "sessionProcessUnobservable": "ps-timeout",
        }
        named: dict[str, Any] = {"sessionProcess": self.process.as_record()}
        for session_id, previous, ending in (
            ("unnamed-before", unnamed, named),
            ("unnamed-end", named, unnamed),
        ):
            with self.subTest(previous=previous, ending=ending):
                store = HookRecordStore(self.state_dir)
                base = hook_record_document("/repo", session_id, "codex")
                store.write(
                    HookRecord.model_validate(
                        {
                            **base,
                            **previous,
                            "state": "waiting",
                            "event": "Stop",
                            "lastActivityAt": "2026-08-25T16:00:00.000000Z",
                        }
                    )
                )

                written = store.write(
                    HookRecord.model_validate(
                        {
                            **base,
                            **ending,
                            "state": "ended",
                            "event": "SessionEnd",
                            "lastActivityAt": "2026-08-25T16:01:00.000000Z",
                        }
                    )
                )

                self.assertEqual("ended", written.state)
                runs, _diagnostics = observe_agent_runs(
                    {"project:example": [observation_target()]},
                    self.state_dir,
                    lookup=present(self.process),
                )
                self.assertEqual([], runs)

    def test_an_older_session_end_beside_a_record_naming_no_process_ends_nothing(
        self,
    ) -> None:
        store = HookRecordStore(self.state_dir)
        base = hook_record_document("/repo", "late-end", "codex")
        store.write(
            HookRecord.model_validate(
                {
                    **base,
                    "sessionProcess": None,
                    "sessionProcessUnobservable": "ps-timeout",
                    "state": "waiting",
                    "event": "Stop",
                    "lastActivityAt": "2026-08-25T16:01:00.000000Z",
                }
            )
        )

        written = store.write(
            HookRecord.model_validate(
                {
                    **base,
                    "sessionProcess": self.process.as_record(),
                    "state": "ended",
                    "event": "SessionEnd",
                    "lastActivityAt": "2026-08-25T16:00:00.000000Z",
                }
            )
        )

        self.assertIsNone(written.state)
        runs, _diagnostics = observe_agent_runs(
            {"project:example": [observation_target()]},
            self.state_dir,
            lookup=present(self.process),
        )
        self.assertEqual(["unknown"], [run.state for run in runs])

    def test_a_session_end_beside_a_record_naming_no_process_keeps_its_sub_agents(
        self,
    ) -> None:
        # Accepted on no contrary evidence, the end is the named process's,
        # so the working sub-agent stays listed until that process is gone
        # (ADR 0095, ADR 0132).
        unnamed: dict[str, Any] = {
            "sessionProcess": None,
            "sessionProcessUnobservable": "ps-timeout",
        }
        named: dict[str, Any] = {"sessionProcess": self.process.as_record()}
        for session_id, previous, ending in (
            ("delegated-unnamed", unnamed, named),
            ("delegated-named", named, unnamed),
        ):
            with self.subTest(previous=previous, ending=ending):
                directory = self.state_dir / session_id
                store = HookRecordStore(directory)
                base = hook_record_document("/repo", session_id, "codex")
                for event, state in (("Stop", "waiting"), ("SubagentStart", "running")):
                    store.write(
                        HookRecord.model_validate(
                            {
                                **base,
                                **previous,
                                "state": state,
                                "event": event,
                                "agentId": "worker"
                                if event == "SubagentStart"
                                else None,
                                "lastActivityAt": "2026-08-25T16:00:00.000000Z",
                            }
                        )
                    )

                written = store.write(
                    HookRecord.model_validate(
                        {
                            **base,
                            **ending,
                            "state": "ended",
                            "event": "SessionEnd",
                            "lastActivityAt": "2026-08-25T16:01:00.000000Z",
                        }
                    )
                )

                self.assertEqual("ended", written.state)
                (blocking,) = sessions_with_live_subagents(
                    [Path("/repo")], [directory], lookup=present(self.process)
                )
                self.assertEqual(
                    (session_id, "ended", self.process, ("worker",)),
                    (
                        blocking.record.session_id,
                        blocking.record.state,
                        blocking.record.process,
                        blocking.record.live_subagents,
                    ),
                )
                self.assertEqual(
                    [],
                    sessions_with_live_subagents(
                        [Path("/repo")], [directory], lookup=absent()
                    ),
                )

    def test_a_previous_record_it_cannot_read_is_no_evidence(self) -> None:
        # The store reads its previous record as a scan does; one a scan
        # refuses, here for want of a cwd, carries nothing into the next
        # record and refuses no end.
        unreadable = {
            "version": 2,
            "sessionId": "damaged",
            "harness": "codex",
            "state": "running",
            "turnStartedAt": "2026-08-24T15:00:00Z",
            "liveSubagents": ["worker"],
            "sessionProcess": CODEX.as_record(),
        }
        path = self.state_dir / "damaged.json"
        for event, state, kept in (
            ("Stop", "waiting", True),
            ("SessionEnd", "ended", False),
        ):
            with self.subTest(event=event):
                path.write_text(json.dumps(unreadable))

                HookRecordStore(self.state_dir).write(
                    HookRecord.model_validate(
                        hook_record_document(
                            "/repo",
                            "damaged",
                            "codex",
                            self.process,
                            state=state,
                            event=event,
                        )
                    )
                )

                self.assertEqual(kept, path.exists())
                if kept:
                    stored = json.loads(path.read_text())
                    self.assertEqual(
                        ("/repo", "waiting", None, []),
                        (
                            stored["cwd"],
                            stored["state"],
                            stored["turnStartedAt"],
                            stored["liveSubagents"],
                        ),
                    )

    def test_session_end_with_a_malformed_binding_still_removes_the_record(
        self,
    ) -> None:
        self.write("ending", "waiting", self.process)

        HookRecordStore(self.state_dir).write(
            HookRecord.model_validate(
                {
                    "version": 2,
                    "sessionId": "ending",
                    "harness": "codex",
                    "cwd": "/repo",
                    "sessionProcess": self.process.as_record(),
                    "lastActivityAt": "2026-08-25T16:00:00Z",
                    "state": "ended",
                    "issueId": "not an id",
                }
            )
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
        # No publisher builds a record naming an unsupported harness; one on
        # disk is the read model's to refuse.
        (self.state_dir / "mystery.json").write_text(
            json.dumps(
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
            HookRecord.model_validate(self.record("waiting", "2026-08-24T15:00:00Z"))
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
            HookRecord.model_validate(self.record("running", "2026-08-24T14:00:00Z"))
        )
        project_session_store(self.worktree).write(
            HookRecord.model_validate(self.record("waiting", "2026-08-24T15:00:00Z"))
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
        # The host's own process table unless a test names what runs.
        self.running: dict[str, Any] = {}

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
            **self.running,
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
        # The first process is gone, as after a `claude --resume` replaced
        # it; one still running keeps its sub-agents (ADR 0107).
        self.process = ProcessIdentity(43, 1, "claude", "Tue Aug 25 02:00:00 2026")
        self.running = {"lookup": absent()}

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

    def test_a_turn_naming_no_process_carries_its_live_subagents(self) -> None:
        # Only a SessionStart drops an unnamed process's listing (ADR 0097);
        # every other event of that process carries it (ADR 0107).
        store = HookRecordStore(self.state_dir)
        for event_name, agent_id in (
            ("UserPromptSubmit", None),
            ("SubagentStart", "agent-1"),
            ("Stop", None),
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

        record = self.stored()
        self.assertEqual(["agent-1"], record["liveSubagents"])
        self.assertEqual("running", record["state"])
        self.assertNotIn("subagentProcesses", record)

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
def test_a_record_with_one_of_process_and_unobservable_reads_the_recorded_reason(
    harness: str, process: ProcessIdentity
) -> None:
    assert classified(harness, process, None, present(process)) == ("live", None)
    assert classified(harness, process, None, absent()) == ("gone", None)
    # A hook that could name no Host Process said why: that is the reason.
    assert classified(harness, None, "isolated-namespace", present(process)) == (
        "unknown",
        "isolated-namespace",
    )
    assert classified(harness, None, "ps-timeout", absent()) == (
        "unknown",
        "ps-timeout",
    )
    assert classified(harness, None, None, absent()) == (
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


# What Claude Code 2.1.289 published under #448, #458 and #488, with what
# Dashpot's publisher received recorded in order
# (docs/spikes/session-start-on-a-live-session-spike.md,
# docs/spikes/conversation-switch-picker-spike.md,
# docs/spikes/idle-session-start-and-fork-spike.md).
MEASUREMENTS = Path(__file__).resolve().parents[1] / "docs/spikes/measurements"
CLAUDE_448_TRACE = MEASUREMENTS / "issue-448-claude-trace.jsonl"
CLAUDE_458_TRACE = MEASUREMENTS / "issue-458-claude-trace.jsonl"
CLAUDE_488_TRACE = MEASUREMENTS / "issue-488-claude-trace.jsonl"
CODEX_448_TRACE = MEASUREMENTS / "issue-448-codex-trace.jsonl"


@dataclass(frozen=True, slots=True)
class MeasuredHook:
    """One hook event Dashpot's publisher received in a measured scenario."""

    receipt: int
    payload: dict[str, Any]
    # The Host Process the publisher identified, as the stored record names it.
    host: ProcessIdentity

    @property
    def agent(self) -> str | None:
        """The Sub-agent whose event this is, if it is one's."""
        return cast("str | None", self.payload.get("agent_id"))


def measured_hooks(scenario: str, trace: Path = CLAUDE_448_TRACE) -> list[MeasuredHook]:
    """The events a measured Claude Code scenario delivered to Dashpot, in order.

    ``PreCompact`` and ``PostCompact`` were observed only: no Dashpot
    integration subscribes them, so the publisher never received them.
    """
    hooks: list[MeasuredHook] = []
    current: str | None = None
    # The start each stored record names for its process; the SessionEnd that
    # removes the last record names none, so a host keeps its first start.
    starts: dict[int, str] = {}
    for line in trace.read_text().splitlines():
        entry = json.loads(line)
        if entry["kind"] == "scenario":
            current = cast("str", entry["name"])
        elif (
            entry["kind"] == "hook" and current == scenario and not entry["observeOnly"]
        ):
            for record in entry["store"]:
                starts.setdefault(record["processPid"], record["processStartedAt"])
            pid = cast("int", entry["hostPid"])
            assert pid in starts, f"no recorded start for #{entry['receipt']}'s host"
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
) -> HookRecord:
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
    "process",
    [
        pytest.param(
            ProcessIdentity(7778, 1, "claude", "Tue Aug 25 03:00:00 2026"),
            id="another-process",
        ),
        pytest.param(None, id="no-process"),
    ],
)
def test_a_compaction_with_no_live_record_of_its_process_runs(
    tmp_path: Path, process: ProcessIdentity | None
) -> None:
    # Nothing says which turn state it keeps; an automatic one falls inside a
    # turn (ADR 0100).
    store = HookRecordStore(tmp_path)
    store.write(claude_event("UserPromptSubmit"))
    store.write(claude_event("Stop"))

    store.write(claude_event("SessionStart", process, source="compact"))

    record = json.loads((tmp_path / "compacting.json").read_text())
    assert (record["state"], record["turnStartedAt"]) == (
        "running",
        record["lastActivityAt"],
    )


@pytest.mark.parametrize(
    "source", ["startup", "resume", "clear", "fork", "unknown-source", None]
)
@pytest.mark.parametrize("previous", ["none", "running", "waiting"])
def test_a_session_start_other_than_a_compaction_begins_no_turn(
    tmp_path: Path, source: str | None, previous: str
) -> None:
    # Whatever its source, and whatever the session's record said before, a
    # SessionStart that is no compaction waits for its prompt (ADR 0106).
    store = HookRecordStore(tmp_path)
    if previous != "none":
        store.write(claude_event("UserPromptSubmit"))
    if previous == "waiting":
        store.write(claude_event("Stop"))
    event = (
        claude_event("SessionStart")
        if source is None
        else claude_event("SessionStart", source=source)
    )

    started = store.write(HookRecord.model_validate(event))

    record = json.loads((tmp_path / "compacting.json").read_text())
    assert started.state == "waiting"
    assert (record["state"], record["turnStartedAt"]) == ("waiting", None)
    assert record["lastSessionStartAt"] == record["lastActivityAt"]
    prompted = json.loads(
        store.write(claude_event("UserPromptSubmit")).path.read_text()
    )
    assert (prompted["state"], prompted["turnStartedAt"]) == (
        "running",
        prompted["lastActivityAt"],
    )


def test_a_session_start_carrying_a_working_sub_agent_runs_with_no_turn_clock(
    tmp_path: Path,
) -> None:
    # The sub-agents it carries hold the session running (ADR 0016, ADR
    # 0097); its own turn has not begun, so the worker's stop leaves it waiting.
    store = HookRecordStore(tmp_path)
    store.write(claude_event("UserPromptSubmit"))
    store.write(claude_event("SubagentStart", agent_id="agent-1"))
    store.write(claude_event("Stop"))

    started = store.write(claude_event("SessionStart", source="resume"))

    record = json.loads(started.path.read_text())
    assert started.state == "running"
    assert (record["liveSubagents"], record["turnStartedAt"]) == (["agent-1"], None)
    stopped = store.write(claude_event("SubagentStop", agent_id="agent-1"))
    assert stopped.state == "waiting"


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
    fresher = json.loads(elsewhere.write(claude_event("Stop")).path.read_text())

    written = here.write(
        claude_event("SessionStart", source="compact"),
        seed=HookRecord.model_validate(fresher),
    )

    record = json.loads(written.path.read_text())
    # Waiting, as the fresher record is; the kept sub-agent holds it running.
    assert (record["state"], record["liveSubagents"]) == ("running", ["agent-1"])
    assert written.state == "running"
    assert record["turnStartedAt"] is None


def codex_event(event_name: str, **fields: str) -> HookRecord:
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
        store.write(codex_event("SessionStart", source="compact")).path.read_text()
    )
    prompted = json.loads(store.write(codex_event("UserPromptSubmit")).path.read_text())

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
    turn = json.loads(store.write(codex_event("UserPromptSubmit")).path.read_text())

    compacted = json.loads(
        store.write(codex_event("SessionStart", source="compact")).path.read_text()
    )
    stopped = json.loads(store.write(codex_event("Stop")).path.read_text())

    assert (compacted["state"], compacted["turnStartedAt"]) == (
        "running",
        turn["turnStartedAt"],
    )
    assert stopped["state"] == "waiting"


def test_a_measured_codex_session_start_waits_only_until_its_prompt(
    tmp_path: Path,
) -> None:
    # Codex 0.160.0 publishes a new thread's SessionStart, `startup` or
    # `clear`, at the start of its first turn: its UserPromptSubmit is the
    # thread's next event (#448), so the wait lasts until the prompt.
    entries = [
        entry
        for entry in map(json.loads, CODEX_448_TRACE.read_text().splitlines())
        if entry["kind"] == "hook"
    ]
    starts = [
        (index, entry)
        for index, entry in enumerate(entries)
        if entry["event"] == "SessionStart"
        and entry["payload"]["source"] in {"startup", "clear"}
    ]
    assert len(starts) == 8
    for index, start in starts:
        session = start["payload"]["session_id"]
        prompt = next(
            entry
            for entry in entries[index + 1 :]
            if entry["payload"]["session_id"] == session
        )
        assert prompt["event"] == "UserPromptSubmit"
        recorded = start["stored"]["sessionProcess"]
        host = ProcessIdentity(recorded["pid"], 1, "codex", recorded["startedAt"])
        directory = tmp_path / session

        published = [
            json.loads(
                publish_hook_event(
                    {**entry["payload"], "cwd": "/repo"},
                    directory,
                    process=host,
                    harness="codex",
                ).path.read_text()
            )
            for entry in (start, prompt)
        ]

        started, prompted = published
        assert (started["state"], started["turnStartedAt"]) == ("waiting", None)
        assert (prompted["state"], prompted["turnStartedAt"]) == (
            "running",
            prompted["lastActivityAt"],
        )


def stored_records(directory: Path) -> dict[str, dict[str, Any]]:
    """Every hook record ``directory`` holds, by session id."""
    return {
        record["sessionId"]: record
        for record in (
            json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))
        )
    }


def replay_store(
    hooks: list[MeasuredHook], directory: Path, *, until: int | None = None
) -> dict[int, dict[str, dict[str, Any]]]:
    """Publish a measured order and return every record the store holds after each receipt."""
    stored: dict[int, dict[str, dict[str, Any]]] = {}
    for hook in hooks:
        if until is not None and hook.receipt > until:
            break
        publish_hook_event(
            {**hook.payload, "cwd": "/repo"},
            directory,
            process=hook.host,
            harness="claude-code",
        )
        stored[hook.receipt] = stored_records(directory)
    return stored


@dataclass(frozen=True, slots=True)
class MeasuredSwitch:
    """One measured Conversation Switch while a worker worked (#448)."""

    hooks: list[MeasuredHook]
    worker: str
    left: str
    entered: str
    end: int
    start: int
    stop: int


def measured_switch(scenario: str, trace: Path = CLAUDE_448_TRACE) -> MeasuredSwitch:
    """The switch a scenario measured: its end, its start, and its worker's stop."""
    hooks = measured_hooks(scenario, trace)
    (worker,) = worker_agents(hooks)
    end = next(
        hook
        for hook in hooks
        if hook.payload["hook_event_name"] == "SessionEnd"
        and hook.payload.get("reason") in {"clear", "resume"}
    )
    start = next(
        hook
        for hook in hooks
        if hook.receipt > end.receipt
        and hook.payload["hook_event_name"] == "SessionStart"
    )
    stop = next(
        hook
        for hook in hooks
        if hook.payload["hook_event_name"] == "SubagentStop" and hook.agent == worker
    )
    return MeasuredSwitch(
        hooks,
        worker,
        left=end.payload["session_id"],
        entered=start.payload["session_id"],
        end=end.receipt,
        start=start.receipt,
        stop=stop.receipt,
    )


# Each measured switch: its SessionEnd, the SessionStart in the same Host
# Process, and the worker's SubagentStop, which names the new session.
MEASURED_SWITCHES = {
    "clear": (162, 163, 174),
    "resume-switch": (217, 218, 229),
    "branch": (261, 262, 273),
    "headless-clear": (380, 382, 398),
}


@pytest.mark.parametrize("scenario", MEASURED_SWITCHES)
def test_a_measured_conversation_switch_moves_its_worker_to_the_new_session(
    tmp_path: Path, scenario: str
) -> None:
    switch = measured_switch(scenario)
    assert (switch.end, switch.start, switch.stop) == MEASURED_SWITCHES[scenario]
    assert switch.left != switch.entered

    stored = replay_store(switch.hooks, tmp_path)

    # The end keeps the worker in an ended record (ADR 0095) ...
    ended = stored[switch.end][switch.left]
    assert (ended["state"], ended["liveSubagents"]) == ("ended", [switch.worker])
    assert ended["reason"] in {"clear", "resume"}
    # ... and the start of the session it goes on under takes it over.
    switched = stored[switch.start]
    assert switch.left not in switched
    entered = switched[switch.entered]
    assert (entered["state"], entered["liveSubagents"]) == ("running", [switch.worker])
    # The worker's stop leaves no record listing it.
    assert all(
        switch.worker not in record["liveSubagents"]
        for record in stored[switch.stop].values()
    )
    # It stops before the new session is prompted, so its own turn has not
    # begun and the session waits (ADR 0106).
    after = stored[switch.stop][switch.entered]
    assert (after["state"], after["liveSubagents"], after["turnStartedAt"]) == (
        "waiting",
        [],
        None,
    )


@pytest.mark.parametrize("scenario", MEASURED_SWITCHES)
def test_a_measured_switch_holds_the_new_session_running_until_its_worker_stops(
    tmp_path: Path, scenario: str
) -> None:
    switch = measured_switch(scenario)
    host = next(hook.host for hook in switch.hooks if hook.receipt == switch.start)
    replay_store(switch.hooks, tmp_path, until=switch.start)

    def publish(event_name: str, **fields: str) -> dict[str, Any]:
        published = publish_hook_event(
            switch_event(switch.entered, event_name, **fields),
            tmp_path,
            process=host,
            harness="claude-code",
        )
        return cast("dict[str, Any]", json.loads(published.path.read_text()))

    # Cleanup sees the worker on the session that runs it, and only there.
    (blocking,) = sessions_with_live_subagents(
        [Path("/repo")], [tmp_path], lookup=present(host)
    )
    assert (blocking.record.session_id, blocking.record.live_subagents) == (
        switch.entered,
        (switch.worker,),
    )
    # A turn of the new session ends while the worker works on.
    publish("UserPromptSubmit")
    stopped = publish("Stop")
    assert (stopped["state"], stopped["liveSubagents"]) == ("running", [switch.worker])

    finished = publish("SubagentStop", agent_id=switch.worker)

    assert (finished["state"], finished["liveSubagents"]) == ("waiting", [])
    assert stored_records(tmp_path).keys() == {switch.entered}
    assert (
        sessions_with_live_subagents([Path("/repo")], [tmp_path], lookup=present(host))
        == []
    )


OTHER_CLAUDE = ProcessIdentity(7778, 1, "claude", "Tue Aug 25 03:00:00 2026")


# Every measured Claude Code scenario whose sessions start: #448's, #458's
# and #488's.
MEASURED_STARTS = [
    *(
        pytest.param(CLAUDE_448_TRACE, scenario, id=f"448-{scenario}")
        for scenario in (
            "compact",
            "compact-worktree",
            "auto-compact",
            "clear",
            "resume-switch",
            "branch",
            "headless-compact",
            "headless-clear",
        )
    ),
    pytest.param(CLAUDE_458_TRACE, "resume-picker", id="458-resume-picker"),
    *(
        pytest.param(CLAUDE_488_TRACE, scenario, id=f"488-{scenario}")
        for scenario in (
            "idle-startup",
            "idle-resume",
            "idle-headless",
            "clear-idle",
            "fork-worker",
        )
    ),
]


@pytest.mark.parametrize(("trace", "scenario"), MEASURED_STARTS)
def test_a_measured_session_start_begins_no_turn(
    tmp_path: Path, trace: Path, scenario: str
) -> None:
    # Every SessionStart but a compaction's reads waiting with no turn clock,
    # or running only for the sub-agents it carries or takes over (ADR 0016,
    # ADR 0106); the session's next prompt starts its turn clock.
    hooks = measured_hooks(scenario, trace)

    stored = replay(hooks, tmp_path)

    starts = [
        hook
        for hook in hooks
        if hook.payload["hook_event_name"] == "SessionStart"
        and hook.payload.get("source") != "compact"
    ]
    assert starts
    for start in starts:
        record = stored[start.receipt]
        assert record["turnStartedAt"] is None
        assert record["state"] == ("running" if record["liveSubagents"] else "waiting")
        prompt = next(
            (
                hook
                for hook in hooks
                if hook.receipt > start.receipt
                and hook.payload["session_id"] == start.payload["session_id"]
                and hook.payload["hook_event_name"]
                in {"UserPromptSubmit", "SessionStart", "SessionEnd"}
            ),
            None,
        )
        if prompt and prompt.payload["hook_event_name"] == "UserPromptSubmit":
            turn = stored[prompt.receipt]
            assert (turn["state"], turn["turnStartedAt"]) == (
                "running",
                turn["lastActivityAt"],
            )


# The #488 scenarios that left a session unprompted, each with the
# SessionStart that began it.
MEASURED_IDLE_STARTS = {
    "idle-startup": (5, "startup"),
    "idle-resume": (25, "resume"),
    "idle-headless": (40, "startup"),
    "clear-idle": (71, "clear"),
}


@pytest.mark.parametrize("scenario", MEASURED_IDLE_STARTS)
def test_a_measured_unprompted_session_reads_waiting(
    tmp_path: Path, scenario: str
) -> None:
    # Claude Code published nothing more while the session sat idle, so the
    # dashboard reads it waiting rather than running from its start.
    receipt, source = MEASURED_IDLE_STARTS[scenario]
    hooks = measured_hooks(scenario, CLAUDE_488_TRACE)
    start = next(hook for hook in hooks if hook.receipt == receipt)
    assert (start.payload["hook_event_name"], start.payload["source"]) == (
        "SessionStart",
        source,
    )

    stored = replay([hook for hook in hooks if hook.receipt <= receipt], tmp_path)

    assert (stored[receipt]["state"], stored[receipt]["turnStartedAt"]) == (
        "waiting",
        None,
    )
    runs, diagnostics = observe_agent_runs(
        {"project:example": [observation_target()]},
        tmp_path,
        lookup=present(start.host),
    )
    assert diagnostics == []
    assert [run.state for run in runs] == ["waiting"]


def test_a_measured_fork_runs_in_another_session_and_takes_nothing_over(
    tmp_path: Path,
) -> None:
    # `/fork` publishes no SessionEnd: the copy starts as a new session in the
    # background daemon's process, and the worker goes on, and stops, in the
    # forking session (#490, ADR 0106).
    hooks = measured_hooks("fork-worker", CLAUDE_488_TRACE)
    (forking_start, fork_start) = (
        hook for hook in hooks if hook.payload["hook_event_name"] == "SessionStart"
    )
    forking, fork = (
        forking_start.payload["session_id"],
        fork_start.payload["session_id"],
    )
    assert fork_start.payload["source"] == "fork"
    assert fork_start.host != forking_start.host
    fork_end = next(
        hook
        for hook in hooks
        if hook.payload["hook_event_name"] == "SessionEnd"
        and hook.payload["session_id"] == fork
    )
    assert fork_end.payload["reason"] == "other"
    # The forking session ends only when the scenario closes it, after the
    # daemon stopped.
    (forking_end,) = (
        hook
        for hook in hooks
        if hook.payload["hook_event_name"] == "SessionEnd"
        and hook.payload["session_id"] == forking
    )
    assert forking_end.receipt > fork_end.receipt
    (worker,) = worker_agents(hooks)
    stop = next(
        hook for hook in hooks if hook.payload["hook_event_name"] == "SubagentStop"
    )
    assert (stop.payload["session_id"], stop.agent, stop.host) == (
        forking,
        worker,
        forking_start.host,
    )

    stored = replay_store(hooks, tmp_path)

    forked = stored[fork_start.receipt]
    assert (forked[fork]["state"], forked[fork]["liveSubagents"]) == ("waiting", [])
    assert (forked[forking]["state"], forked[forking]["liveSubagents"]) == (
        "running",
        [worker],
    )
    stopped = stored[stop.receipt]
    assert all(worker not in record["liveSubagents"] for record in stopped.values())
    assert (stopped[forking]["state"], stopped[fork]["state"]) == ("waiting", "waiting")


@pytest.mark.parametrize(
    ("trace", "scenario"),
    [
        *(
            pytest.param(CLAUDE_448_TRACE, scenario, id=f"448-{scenario}")
            for scenario in MEASURED_SWITCHES
        ),
        pytest.param(CLAUDE_458_TRACE, "resume-picker", id="458-resume-picker"),
    ],
)
def test_a_measured_switch_with_no_worker_reads_waiting(
    tmp_path: Path, trace: Path, scenario: str
) -> None:
    # The same switch, had the session delegated to no worker: nothing holds
    # the new session running before its next prompt (ADR 0106).
    switch = measured_switch(scenario, trace)

    stored = replay_store(
        [hook for hook in switch.hooks if hook.agent != switch.worker],
        tmp_path,
        until=switch.start,
    )

    assert switch.left not in stored[switch.start]
    entered = stored[switch.start][switch.entered]
    assert (entered["state"], entered["turnStartedAt"]) == ("waiting", None)


def switch_event(session_id: str, event_name: str, **fields: str) -> dict[str, Any]:
    """A hook event of ``session_id`` at ``/repo``."""
    return {
        "session_id": session_id,
        "cwd": "/repo",
        "hook_event_name": event_name,
        **fields,
    }


def publish_switch(
    directory: Path,
    session_id: str,
    event_name: str,
    process: ProcessIdentity | None = CLAUDE,
    harness: Harness = "claude-code",
    **fields: str,
) -> None:
    """Publish one hook event of ``session_id`` to the one store ``directory``."""
    publish_hook_event(
        switch_event(session_id, event_name, **fields),
        directory,
        process=process,
        harness=harness,
        lookup=absent() if process is None else present(process),
    )


def left_with_worker(
    directory: Path,
    process: ProcessIdentity = CLAUDE,
    harness: Harness = "claude-code",
    reason: str = "clear",
) -> None:
    """Start ``agent-1`` in session ``left``, then end ``left`` with ``reason`` while it works."""
    publish_switch(directory, "left", "UserPromptSubmit", process, harness)
    publish_switch(
        directory, "left", "SubagentStart", process, harness, agent_id="agent-1"
    )
    publish_switch(directory, "left", "Stop", process, harness)
    publish_switch(directory, "left", "SessionEnd", process, harness, reason=reason)


@pytest.mark.parametrize(
    ("process", "source", "reason"),
    [
        pytest.param(
            OTHER_CLAUDE,
            "clear",
            "clear",
            id="another-process",
        ),
        pytest.param(None, "clear", "clear", id="no-process"),
        pytest.param(CLAUDE, "startup", "clear", id="a-start-that-is-no-switch"),
        pytest.param(CLAUDE, "compact", "clear", id="a-compaction"),
        pytest.param(
            CLAUDE, "clear", "prompt_input_exit", id="an-end-that-is-no-switch"
        ),
    ],
)
def test_only_a_switch_of_the_same_process_takes_over_an_ended_sessions_worker(
    tmp_path: Path, process: ProcessIdentity | None, source: str, reason: str
) -> None:
    left_with_worker(tmp_path, reason=reason)

    publish_switch(tmp_path, "entered", "SessionStart", process, source=source)

    records = stored_records(tmp_path)
    assert records["entered"]["liveSubagents"] == []
    assert (records["left"]["state"], records["left"]["liveSubagents"]) == (
        "ended",
        ["agent-1"],
    )


def test_a_codex_threads_clear_leaves_an_unloaded_threads_worker_where_it_is(
    tmp_path: Path,
) -> None:
    # A daemon unloads a lead with `reason` `other` while its worker works on
    # under the lead's own id, and another thread's `/clear` publishes
    # SessionStart `clear` from the same daemon (#448, #420).
    left_with_worker(tmp_path, CODEX, "codex", reason="other")

    publish_switch(tmp_path, "entered", "SessionStart", CODEX, "codex", source="clear")
    publish_switch(tmp_path, "left", "SubagentStop", CODEX, "codex", agent_id="agent-1")

    records = stored_records(tmp_path)
    assert records.keys() == {"entered"}
    assert records["entered"]["liveSubagents"] == []


def test_a_switch_takes_over_a_worker_kept_at_another_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The session the process left ended at `a`; the one it switched to
    # starts at `b`, and the worker stops under the new session's id.
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))
    a, b = two_worktrees(tmp_path)

    def publish(at: Path, session_id: str, event_name: str, **fields: str) -> Path:
        return publish_hook_event(
            {
                "session_id": session_id,
                "cwd": str(at),
                "hook_event_name": event_name,
                **fields,
            },
            process=CLAUDE,
            harness="claude-code",
            lookup=present(CLAUDE),
        ).path

    publish(a, "left", "UserPromptSubmit")
    publish(a, "left", "SubagentStart", agent_id="agent-1")
    publish(a, "left", "SessionEnd", reason="resume")

    entered = json.loads(
        publish(b, "entered", "SessionStart", source="fork").read_text()
    )

    assert entered["liveSubagents"] == ["agent-1"]
    assert stored_records(session_directory(a)) == {}

    stopped = publish(b, "entered", "SubagentStop", agent_id="agent-1")

    assert stopped.parent == session_directory(b)
    assert json.loads(stopped.read_text())["liveSubagents"] == []


def test_a_workers_stop_before_the_switchs_start_clears_the_session_it_left(
    tmp_path: Path,
) -> None:
    # The worker's stop names the new session, whose SessionStart has not
    # been written yet: no record is invented for it, the ended record lets
    # the worker go, and the start that follows has nothing to take over.
    left_with_worker(tmp_path)

    publish_switch(tmp_path, "entered", "SubagentStop", agent_id="agent-1")

    assert stored_records(tmp_path) == {}

    publish_switch(tmp_path, "entered", "SessionStart", source="clear")

    assert stored_records(tmp_path)["entered"]["liveSubagents"] == []


def test_a_stop_clears_a_worker_an_ended_record_kept_before_this_rule(
    tmp_path: Path,
) -> None:
    # A record ended before its publisher kept the end's `reason` gives no
    # evidence of a switch, so nothing takes it over; the worker's stop under
    # another session of the same process still clears it.
    left_with_worker(tmp_path)
    path = tmp_path / "left.json"
    unreasoned = json.loads(path.read_text())
    del unreasoned["reason"]
    path.write_text(json.dumps(unreasoned))
    assert classify_hook_record(
        unreasoned, LivenessProbe(present(CLAUDE))
    ).retains_subagents

    publish_switch(tmp_path, "entered", "SessionStart", source="clear")
    assert stored_records(tmp_path)["left"]["liveSubagents"] == ["agent-1"]

    publish_switch(tmp_path, "entered", "SubagentStop", agent_id="agent-1")

    assert stored_records(tmp_path).keys() == {"entered"}


def test_a_stop_leaves_another_live_sessions_record_and_another_process_alone(
    tmp_path: Path,
) -> None:
    # Only ended records of the stop's own Host Process let a stopped
    # sub-agent go; a live session's records are not this rule's to change.
    publish_switch(tmp_path, "live", "UserPromptSubmit")
    publish_switch(tmp_path, "live", "SubagentStart", agent_id="agent-1")
    publish_switch(tmp_path, "elsewhere", "UserPromptSubmit", OTHER_CLAUDE)
    publish_switch(
        tmp_path, "elsewhere", "SubagentStart", OTHER_CLAUDE, agent_id="agent-1"
    )
    publish_switch(tmp_path, "elsewhere", "SessionEnd", OTHER_CLAUDE, reason="clear")
    publish_switch(tmp_path, "stopping", "UserPromptSubmit")

    publish_switch(tmp_path, "stopping", "SubagentStop", agent_id="agent-1")

    records = stored_records(tmp_path)
    assert records["live"]["liveSubagents"] == ["agent-1"]
    assert records["elsewhere"]["liveSubagents"] == ["agent-1"]


def test_a_stop_from_an_unnamed_process_leaves_every_ended_record_alone(
    tmp_path: Path,
) -> None:
    # Without a Host Process to bound it, a stop is no evidence about any
    # ended record, which keeps the worker until a named stop or its exit.
    left_with_worker(tmp_path)

    publish_switch(tmp_path, "entered", "SubagentStop", None, agent_id="agent-1")

    assert stored_records(tmp_path)["left"]["liveSubagents"] == ["agent-1"]


def test_an_unreadable_record_is_skipped_by_a_switch_and_left_by_a_release(
    tmp_path: Path,
) -> None:
    left_with_worker(tmp_path)
    unreadable = tmp_path / "broken.json"
    unreadable.write_text("{not json")
    by = build_hook_record(
        switch_event("entered", "SessionStart", source="clear"),
        process=CLAUDE,
        harness="claude-code",
    )

    assert not HookRecordStore(tmp_path).release_subagents(
        "broken", ["agent-1"], HookRecord.model_validate(by), session_id="broken"
    )

    publish_switch(tmp_path, "entered", "SessionStart", source="clear")

    entered = json.loads((tmp_path / "entered.json").read_text())
    assert entered["liveSubagents"] == ["agent-1"]
    assert not (tmp_path / "left.json").exists()
    assert unreadable.read_text() == "{not json"


def test_releasing_sub_agents_changes_only_an_ended_record_of_the_same_process(
    tmp_path: Path,
) -> None:
    store = HookRecordStore(tmp_path)
    by = build_hook_record(
        switch_event("entered", "SessionStart", source="clear"),
        process=CLAUDE,
        harness="claude-code",
    )
    store.write(
        build_hook_record(
            switch_event("live", "UserPromptSubmit"), CLAUDE, "claude-code"
        )
    )
    store.write(
        build_hook_record(
            switch_event("live", "SubagentStart", agent_id="agent-1"),
            CLAUDE,
            "claude-code",
        )
    )
    for agent in ("agent-1", "agent-2"):
        store.write(
            build_hook_record(
                switch_event("left", "SubagentStart", agent_id=agent),
                CLAUDE,
                "claude-code",
            )
        )
    store.write(
        build_hook_record(
            switch_event("left", "SessionEnd", reason="clear"), CLAUDE, "claude-code"
        )
    )
    codex_by = by.model_copy(update={"harness": "codex"})
    other_by = build_hook_record(
        switch_event("entered", "SessionStart", source="clear"),
        process=OTHER_CLAUDE,
        harness="claude-code",
    )

    assert not store.release_subagents(
        "live", ["agent-1"], HookRecord.model_validate(by), session_id="live"
    )
    assert not store.release_subagents(
        "missing", ["agent-1"], HookRecord.model_validate(by), session_id="missing"
    )
    assert not store.release_subagents(
        "left", ["agent-1"], HookRecord.model_validate(codex_by), session_id="left"
    )
    assert not store.release_subagents(
        "left", ["agent-1"], HookRecord.model_validate(other_by), session_id="left"
    )
    assert not store.release_subagents(
        "left", ["agent-3"], HookRecord.model_validate(by), session_id="left"
    )
    assert store.release_subagents(
        "left", ["agent-1"], HookRecord.model_validate(by), session_id="left"
    )
    assert stored_records(tmp_path)["left"]["liveSubagents"] == ["agent-2"]
    assert store.release_subagents(
        "left", ["agent-2"], HookRecord.model_validate(by), session_id="left"
    )

    records = stored_records(tmp_path)
    assert records.keys() == {"live"}
    assert records["live"]["liveSubagents"] == ["agent-1"]


def test_releasing_a_left_behind_sub_agent_changes_only_the_sessions_own_live_record(
    tmp_path: Path,
) -> None:
    store = HookRecordStore(tmp_path)
    for agent in ("agent-1", "agent-2"):
        store.write(
            build_hook_record(
                switch_event("moved", "SubagentStart", agent_id=agent),
                CLAUDE,
                "claude-code",
            )
        )
    left_with_worker(tmp_path)
    before = stored_records(tmp_path)["moved"]

    def stop(session_id: str, process: ProcessIdentity | None = CLAUDE) -> Any:
        return build_hook_record(
            switch_event(session_id, "SubagentStop", agent_id="agent-1"),
            process,
            "claude-code",
        )

    by = stop("moved")
    assert not store.release_left_behind(
        "left", ["agent-1"], HookRecord.model_validate(stop("left"))
    )
    assert not store.release_left_behind(
        "missing", ["agent-1"], HookRecord.model_validate(by)
    )
    assert not store.release_left_behind(
        "moved", ["agent-1"], HookRecord.model_validate(stop("other"))
    )
    assert not store.release_left_behind(
        "moved", ["agent-1"], by.model_copy(update={"harness": "codex"})
    )
    assert not store.release_left_behind(
        "moved", ["agent-1"], HookRecord.model_validate(stop("moved", OTHER_CLAUDE))
    )
    assert not store.release_left_behind(
        "moved", ["agent-1"], HookRecord.model_validate(stop("moved", None))
    )
    assert not store.release_left_behind(
        "moved", ["agent-3"], HookRecord.model_validate(by)
    )
    assert stored_records(tmp_path)["moved"] == before

    assert store.release_left_behind(
        "moved", ["agent-1"], HookRecord.model_validate(by)
    )
    assert stored_records(tmp_path)["moved"] == {**before, "liveSubagents": ["agent-2"]}
    assert store.release_left_behind(
        "moved", ["agent-2"], HookRecord.model_validate(by)
    )

    # A live record listing none stays: only its session's end or a prune
    # removes it.
    records = stored_records(tmp_path)
    assert records["moved"] == {**before, "liveSubagents": []}
    assert records["left"]["liveSubagents"] == ["agent-1"]
