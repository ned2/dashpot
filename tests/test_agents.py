from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typing_extensions import override

from dashpot.agents import observe_agent_runs
from dashpot.hook_records import write_hook_record
from dashpot.model import ObservationTarget
from dashpot.processes import ProcessIdentity
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
from factories import hook_record_document, observation_target
from helpers import absent, present, table_lookup, unobservable


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
        linked = observation_target("/repo-linked", branch="feature")
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
            session_process=SessionProcess(
                pid=process.pid, started_at=process.started_at
            ),
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
            hook_record_document(
                cwd,
                session_id,
                "codex",
                self.process,
                state=state,
                at="2026-08-24T15:00:00Z",
                event="Stop" if state == "waiting" else "PreToolUse",
            ),
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
        target = observation_target(str(self.worktree), availability="unavailable")

        runs, diagnostics = observe_agent_runs(
            {"project:example": [target]},
            self.state_dir,
            lookup=present(self.process),
        )

        self.assertEqual([], runs)
        self.assertEqual([], diagnostics)


class SessionIdentityCorrelationTests(unittest.TestCase):
    """Work Store runs join hook Agent Sessions by Agent Session Identity."""

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

    def targets(self) -> dict[str, list[ObservationTarget]]:
        return {"project:example": [observation_target(str(self.worktree))]}

    def write_hook(
        self,
        session_id: str,
        harness: str = "codex",
        process: ProcessIdentity | None = None,
        state: str = "running",
        at: str = "2026-08-24T15:00:00Z",
    ) -> None:
        write_hook_record(
            hook_record_document(
                self.worktree,
                session_id,
                harness,
                process,
                state=state,
                at=at,
            ),
            self.state_dir,
        )

    def record_work(
        self,
        session_key: str,
        harness: str = "codex",
        session_id: str | None = None,
        process: ProcessIdentity | None = None,
        worktree: Path | None = None,
    ) -> ActiveWork:
        worktree = worktree or self.worktree
        work = ActiveWork(
            session_key=session_key,
            harness=harness,
            session_label=f"{harness} session {session_id}",
            session_process=(
                SessionProcess(pid=process.pid, started_at=process.started_at)
                if process
                else None
            ),
            issue_id="I_example/project#7",
            issue_reference="example/project#7",
            binding_provenance="explicit-reference",
            started_at="2026-08-24T14:00:00Z",
            working_directory=str(worktree),
            branch="feature",
            session_id=session_id,
        )
        WorkStore(worktree).start(work)
        return work

    def test_run_without_a_process_adopts_hook_state_by_session_identity(
        self,
    ) -> None:
        work = self.record_work("codex-session-abc", session_id="thread-1")
        self.write_hook("thread-1", process=self.process)

        runs, diagnostics = observe_agent_runs(
            self.targets(), self.state_dir, lookup=present(self.process)
        )

        self.assertEqual([], diagnostics)
        self.assertEqual([work.run_id], [run.id for run in runs])
        self.assertEqual("running", runs[0].state)
        self.assertEqual("I_example/project#7", runs[0].issue_id)
        self.assertEqual("2026-08-24T15:00:00Z", runs[0].last_activity_at)

    def test_one_session_recorded_by_two_routes_is_a_conflict(self) -> None:
        # The same session opted in at one Worktree by its process and at
        # another by Agent Session Identity alone; its hook record carries
        # both, which is how the two records are known to be one session.
        other = self.root / "repo-linked"
        other.mkdir()
        self.record_work(
            "codex-42-abcd1234", session_id="thread-1", process=self.process
        )
        self.record_work("codex-session-abc", session_id="thread-1", worktree=other)
        self.write_hook("thread-1", process=self.process)

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

        # Both records adopt the one hook session's state; each is listed.
        self.assertEqual(["running", "running"], [run.state for run in runs])
        # Both records carry the Agent Session Identity, so neither takes the
        # ambiguous process route: the conflict is the only diagnostic.
        self.assertEqual(
            ["work-session-conflict"], [diagnostic.code for diagnostic in diagnostics]
        )

    def test_session_identity_is_scoped_to_its_harness(self) -> None:
        self.record_work("codex-session-abc", session_id="shared-id")
        self.write_hook("shared-id", harness="claude-code", process=self.process)

        runs, _ = observe_agent_runs(
            self.targets(), self.state_dir, lookup=present(self.process)
        )

        # The Codex run cannot adopt a Claude Code session's state, and the
        # Claude Code session stays listed as its own unbound session.
        self.assertEqual(
            {("codex", "unknown"), ("claude-code", "running")},
            {(run.harness, run.state) for run in runs},
        )

    def test_hook_record_without_a_process_is_joined_by_identity_only(
        self,
    ) -> None:
        work = self.record_work("codex-session-abc", session_id="thread-2")
        self.write_hook("thread-2", process=None, state="waiting")

        runs, diagnostics = observe_agent_runs(
            self.targets(), self.state_dir, lookup=absent()
        )

        self.assertEqual([work.run_id], [run.id for run in runs])
        # Session Liveness is unknown for both records, which is never
        # evidence that the session ended: the run is listed, not orphaned.
        self.assertEqual("unknown", runs[0].state)
        self.assertNotIn(
            "work-session-orphaned", [diagnostic.code for diagnostic in diagnostics]
        )

    def test_process_keyed_run_with_identity_prefers_identity_then_process(
        self,
    ) -> None:
        work = self.record_work(
            "codex-42-abcd1234", session_id="thread-3", process=self.process
        )
        self.write_hook("thread-3", process=self.process, state="waiting")
        # A fresher resumed session shares the host process; a run that
        # carries its Agent Session Identity must not adopt it by process.
        self.write_hook(
            "thread-3-resumed",
            process=self.process,
            state="running",
            at="2026-08-24T16:00:00Z",
        )

        runs, diagnostics = observe_agent_runs(
            self.targets(), self.state_dir, lookup=present(self.process)
        )

        self.assertEqual([], diagnostics)
        by_id = {run.id: run for run in runs}
        self.assertEqual("waiting", by_id[work.run_id].state)
        # The resumed session was not consumed and stays listed on its own.
        self.assertIn("codex-session:thread-3-resumed", by_id)

    def test_ambiguous_process_key_adopts_the_freshest_and_is_reported(
        self,
    ) -> None:
        # A resumed session reuses its host process, so two hook records
        # share the run's process key; only the process route is ambiguous.
        work = self.record_work("codex-42-abcd1234", process=self.process)
        self.write_hook("thread-4", process=self.process, state="waiting")
        self.write_hook(
            "thread-4-resumed",
            process=self.process,
            state="running",
            at="2026-08-24T16:00:00Z",
        )

        runs, diagnostics = observe_agent_runs(
            self.targets(), self.state_dir, lookup=present(self.process)
        )

        by_id = {run.id: run for run in runs}
        self.assertEqual("running", by_id[work.run_id].state)
        self.assertEqual("2026-08-24T16:00:00Z", by_id[work.run_id].last_activity_at)
        # The freshest session was consumed by the run; the stale one stays
        # listed as its own unbound session.
        self.assertIn("codex-session:thread-4", by_id)
        self.assertNotIn("codex-session:thread-4-resumed", by_id)
        ambiguity = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.code == "agent-session-process-ambiguous"
        ]
        self.assertEqual(1, len(ambiguity))
        self.assertEqual("warning", ambiguity[0].severity)
        self.assertEqual("agent-sessions", ambiguity[0].source)
        self.assertIn("thread-4-resumed", ambiguity[0].message)
