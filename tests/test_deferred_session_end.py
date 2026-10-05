"""A managed Codex daemon's ``SessionEnd`` ends a run only if the daemon keeps running (#356).

The pinned release publishes the same ``SessionEnd`` for a thread its managed
daemon unloads as for every thread the daemon holds when it is stopped or
restarted, and waits for the hook before it exits. The publisher hands such an
end to a settler; each test replays the hooks and the daemon's fate in the
order the release produces them (ADR 0086).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from dashpot import hook
from dashpot.core.event_log import EventLogDestination
from dashpot.core.model import AgentRun, Harness
from dashpot.event_logs import LEVEL_VARIABLE, route_event_log
from dashpot.sessions.agent_runs import observe_agent_runs
from dashpot.sessions.deferred_end import (
    POLL_SECONDS,
    SETTLE_SECONDS,
    DeferredEnd,
    settle_session_end,
    settler_command,
    spawn_settler,
)
from dashpot.sessions.harnesses import is_codex_managed_daemon
from dashpot.sessions.hook_publish import HookPublication, publish_hook_event
from dashpot.sessions.hook_records import session_directory
from dashpot.sessions.processes import (
    ProcessAbsent,
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
    ProcessUnobservable,
)
from dashpot.sessions.work import relocate_issue_work, start_issue_work, stop_issue_work
from dashpot.sessions.work_store import ActiveWork, SessionProcess, WorkStore
from factories import CLAUDE, hook_record
from helpers import absent, present, table_lookup, unobservable
from test_work import (
    CLAUDE_ENVIRON,
    CLAUDE_SESSION,
    CODEX_SESSION,
    repository,
    target,
    two_worktrees,
)

# The managed daemon's argv as the pinned release starts it.
DAEMON_ARGUMENTS = (
    "/home/u/.codex/packages/standalone/app-server-daemon/releases/0.160.0/bin/codex"
    " app-server --remote-control --listen unix:// --managed-daemon"
)
DAEMON = ProcessIdentity(
    4242, 1, "codex", "Thu Oct 01 09:00:00 2026", arguments=DAEMON_ARGUMENTS
)
# The daemon a restart starts in its place.
REPLACEMENT = ProcessIdentity(
    5353, 1, "codex", "Thu Oct 01 09:30:00 2026", arguments=DAEMON_ARGUMENTS
)
# A second root thread loaded on the same daemon.
SIBLING = "01a05099-1563-79a3-8504-e30d50949cb7"
UNBOUND = "01a05099-1563-79a3-8504-e30d50949cc8"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


@dataclass
class Settlers:
    """Stand in for the detached settler: record each end handed to it."""

    started: list[DeferredEnd] = field(default_factory=list)

    def __call__(self, deferred: DeferredEnd) -> None:
        self.started.append(deferred)


@dataclass
class Clock:
    """A monotonic clock that advances only when the settler sleeps."""

    now: float = 100.0
    slept: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def bind(root: Path, session_id: str, host: ProcessIdentity, issue: str) -> ActiveWork:
    """Opt a thread hosted by ``host`` into Issue work at ``root``."""
    hook_record(root, session_id, "codex", host)
    start_issue_work(
        root, issue, lookup=present(host), environ={"CODEX_THREAD_ID": session_id}
    )
    return next(
        work for work in WorkStore(root).active()[0] if work.session_id == session_id
    )


def session_end(
    root: Path,
    session_id: str,
    host: ProcessIdentity,
    settle: Settlers,
    *,
    harness: Harness = "codex",
) -> HookPublication:
    """Publish a thread's ``SessionEnd`` from its host, as the release does."""
    return publish_hook_event(
        {"session_id": session_id, "cwd": str(root), "hook_event_name": "SessionEnd"},
        process=host,
        harness=harness,
        lookup=present(host),
        settle=settle,
    )


def settle(
    deferred: DeferredEnd, lookup: ProcessLookup
) -> list[tuple[Path, ActiveWork]]:
    """Run the settler to its decision without waiting in real time."""
    clock = Clock()
    return settle_session_end(deferred, lookup, clock=clock, sleep=clock.sleep)


def runs(root: Path, lookup: ProcessLookup, *others: Path) -> list[AgentRun]:
    """The Agent Runs observation shows at ``root`` and any other Worktrees."""
    observed, _diagnostics = observe_agent_runs(
        {"project:example": [target(worktree) for worktree in (root, *others)]},
        Path("/nonexistent-global-store"),
        lookup=lookup,
    )
    return [run for run in observed if run.issue_id is not None]


# --- The Harness Adapter names the managed daemon by its argv ---------------


@pytest.mark.parametrize(
    ("arguments", "managed"),
    [
        pytest.param(DAEMON_ARGUMENTS, True, id="managed-daemon"),
        pytest.param(
            "codex app-server --listen unix:// --managed-daemon", True, id="bare"
        ),
        pytest.param("codex app-server --listen unix://", False, id="unmanaged"),
        pytest.param("codex exec 'fix it'", False, id="exec"),
        pytest.param("codex", False, id="standalone"),
        pytest.param("codex --managed-daemon", False, id="not-an-app-server"),
        pytest.param(None, False, id="no-arguments"),
    ],
)
def test_only_a_managed_daemon_defers_its_session_end(
    arguments: str | None, managed: bool
) -> None:
    process = ProcessIdentity(1, 1, "codex", "Thu Oct 01 09:00:00 2026", arguments)
    assert is_codex_managed_daemon(process) is managed
    claude = ProcessIdentity(1, 1, "claude", "Thu Oct 01 09:00:00 2026", arguments)
    assert is_codex_managed_daemon(claude) is False


# --- The publisher hands a bound thread's end to a settler -------------------


def test_a_daemon_session_end_leaves_its_run_to_a_settler(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    work = bind(a, CODEX_SESSION, DAEMON, "build-observer")
    settlers = Settlers()

    publication = session_end(b, CODEX_SESSION, DAEMON, settlers)

    assert (publication.state, publication.work, publication.issue_id) == (
        "ended",
        "deferred",
        work.issue_id,
    )
    assert WorkStore(a).active()[0] == [work]
    (deferred,) = settlers.started
    assert deferred.harness == "codex"
    assert deferred.session_id == CODEX_SESSION
    assert deferred.host == SessionProcess(pid=DAEMON.pid, started_at=DAEMON.started_at)
    assert deferred.worktrees == (str(a), str(b))
    assert deferred.cwd == str(b)
    assert deferred.ended_at is not None
    assert datetime.fromisoformat(deferred.ended_at) >= datetime.fromisoformat(
        work.started_at
    )
    # The record still says the thread ended, and is pruned as before.
    assert not session_directory(b).joinpath(f"{CODEX_SESSION}.json").exists()


def test_an_unbound_daemon_thread_needs_no_settler(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo").resolve()
    bind(root, CODEX_SESSION, DAEMON, "build-observer")
    hook_record(root, UNBOUND, "codex", DAEMON)
    settlers = Settlers()

    publication = session_end(root, UNBOUND, DAEMON, settlers)

    assert (publication.work, publication.issue_id) == ("unchanged", None)
    assert settlers.started == []


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param("codex exec 'fix it'", id="exec"),
        pytest.param("codex", id="standalone-exit"),
        pytest.param("codex app-server --listen unix://", id="unmanaged-app-server"),
    ],
)
def test_any_other_codex_host_ends_its_run_at_once(
    tmp_path: Path, arguments: str
) -> None:
    root = repository(tmp_path / "repo").resolve()
    host = ProcessIdentity(4242, 1, "codex", "Thu Oct 01 09:00:00 2026", arguments)
    work = bind(root, CODEX_SESSION, host, "build-observer")
    settlers = Settlers()

    publication = session_end(root, CODEX_SESSION, host, settlers)

    assert (publication.work, publication.issue_id) == ("ended", work.issue_id)
    assert WorkStore(root).active() == ([], [])
    assert settlers.started == []


def test_a_claude_code_session_end_still_ends_its_run(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo").resolve()
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)
    start_issue_work(
        root, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )
    settlers = Settlers()

    publication = session_end(
        root, CLAUDE_SESSION, CLAUDE, settlers, harness="claude-code"
    )

    assert publication.work == "ended"
    assert WorkStore(root).active() == ([], [])
    assert settlers.started == []


def test_a_declared_relocation_is_still_preserved_without_a_settler(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    bind(a, CODEX_SESSION, DAEMON, "build-observer")
    relocate_issue_work(
        a, b, lookup=present(DAEMON), environ={"CODEX_THREAD_ID": CODEX_SESSION}
    )
    (pending,) = WorkStore(a).active()[0]
    settlers = Settlers()

    publication = session_end(a, CODEX_SESSION, DAEMON, settlers)

    assert publication.work == "unchanged"
    assert settlers.started == []
    assert WorkStore(a).active()[0] == [pending]


def test_a_settler_that_cannot_start_fails_the_hook_and_leaves_the_run(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo").resolve()
    work = bind(root, CODEX_SESSION, DAEMON, "build-observer")

    def unstartable(_deferred: DeferredEnd) -> None:
        raise OSError("no settler")

    with pytest.raises(OSError, match="no settler"):
        publish_hook_event(
            {
                "session_id": CODEX_SESSION,
                "cwd": str(root),
                "hook_event_name": "SessionEnd",
            },
            process=DAEMON,
            harness="codex",
            lookup=present(DAEMON),
            settle=unstartable,
        )

    # The record was written first; the run waits, an orphan once the daemon goes.
    assert not session_directory(root).joinpath(f"{CODEX_SESSION}.json").exists()
    assert WorkStore(root).active()[0] == [work]
    assert [run.orphaned for run in runs(root, absent())] == [True]


# --- The settler decides by the daemon's fate --------------------------------


def deferred_end(tmp_path: Path) -> tuple[Path, ActiveWork, DeferredEnd]:
    """A bound thread whose daemon published its ``SessionEnd``."""
    root = repository(tmp_path / "repo").resolve()
    work = bind(root, CODEX_SESSION, DAEMON, "build-observer")
    settlers = Settlers()
    session_end(root, CODEX_SESSION, DAEMON, settlers)
    (deferred,) = settlers.started
    return root, work, deferred


def test_an_unload_ends_the_run_once_the_daemon_outlives_the_window(
    tmp_path: Path,
) -> None:
    root, work, deferred = deferred_end(tmp_path)
    clock = Clock()

    ended = settle_session_end(
        deferred, present(DAEMON), clock=clock, sleep=clock.sleep
    )

    assert ended == [(root, work)]
    assert WorkStore(root).active() == ([], [])
    assert runs(root, present(DAEMON)) == []
    assert sum(clock.slept) >= SETTLE_SECONDS
    assert set(clock.slept) == {POLL_SECONDS}


@pytest.mark.parametrize(
    "lookup",
    [
        pytest.param(absent(), id="stopped"),
        pytest.param(present(REPLACEMENT), id="pid-reused-by-the-replacement"),
        pytest.param(table_lookup({REPLACEMENT.pid: REPLACEMENT}), id="restarted"),
    ],
)
def test_a_stop_or_restart_leaves_the_run_orphaned(
    tmp_path: Path, lookup: ProcessLookup
) -> None:
    root, work, deferred = deferred_end(tmp_path)
    clock = Clock()

    ended = settle_session_end(deferred, lookup, clock=clock, sleep=clock.sleep)

    assert ended == []
    assert clock.slept == []
    assert WorkStore(root).active()[0] == [work]
    (run,) = runs(root, lookup)
    assert (run.issue_id, run.orphaned) == (work.issue_id, True)


def test_a_daemon_that_exits_inside_the_window_orphans_the_run(
    tmp_path: Path,
) -> None:
    root, work, deferred = deferred_end(tmp_path)
    fates: Iterator[ProcessObservation] = iter(
        [ProcessPresent(DAEMON), ProcessPresent(DAEMON), ProcessPresent(REPLACEMENT)]
    )
    clock = Clock()

    ended = settle_session_end(
        deferred, lambda _pid: next(fates), clock=clock, sleep=clock.sleep
    )

    assert ended == []
    assert clock.slept == [POLL_SECONDS, POLL_SECONDS]
    assert WorkStore(root).active()[0] == [work]


def test_an_unobservable_daemon_ends_nothing(tmp_path: Path) -> None:
    root, work, deferred = deferred_end(tmp_path)
    clock = Clock()

    ended = settle_session_end(
        deferred, unobservable("ps-timeout"), clock=clock, sleep=clock.sleep
    )

    assert ended == []
    # Unknown is never evidence the daemon was stopped: the settler waited
    # out the whole window before leaving the run.
    assert sum(clock.slept) >= SETTLE_SECONDS
    assert WorkStore(root).active()[0] == [work]


def test_a_daemon_unobservable_then_gone_orphans_the_run(tmp_path: Path) -> None:
    root, work, deferred = deferred_end(tmp_path)
    fates: Iterator[ProcessObservation] = iter(
        [
            ProcessUnobservable(DAEMON.pid, "ps-timeout"),
            ProcessUnobservable(DAEMON.pid, "ps-timeout"),
            ProcessAbsent(DAEMON.pid),
        ]
    )
    clock = Clock()

    ended = settle_session_end(
        deferred, lambda _pid: next(fates), clock=clock, sleep=clock.sleep
    )

    assert ended == []
    assert clock.slept == [POLL_SECONDS, POLL_SECONDS]
    assert WorkStore(root).active()[0] == [work]


def test_a_settler_runs_again_without_effect(tmp_path: Path) -> None:
    root, _work, deferred = deferred_end(tmp_path)
    settle(deferred, present(DAEMON))

    assert settle(deferred, present(DAEMON)) == []
    assert WorkStore(root).active() == ([], [])


def test_a_work_start_inside_the_window_wins(tmp_path: Path) -> None:
    root, work, deferred = deferred_end(tmp_path)
    # The thread is resumed on the daemon and opts in again before the window ends.
    restarted = bind(root, CODEX_SESSION, DAEMON, "fix-crash")
    assert restarted.started_at > work.started_at

    assert settle(deferred, present(DAEMON)) == []
    assert WorkStore(root).active()[0] == [restarted]


def test_a_work_stop_inside_the_window_wins(tmp_path: Path) -> None:
    root, work, deferred = deferred_end(tmp_path)
    stop_issue_work(root, session_key=work.session_key, lookup=absent())

    assert settle(deferred, present(DAEMON)) == []
    assert WorkStore(root).active() == ([], [])


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root writes through directory permissions",
)
def test_a_settler_that_cannot_write_the_work_store_leaves_the_run(
    tmp_path: Path,
) -> None:
    root, work, deferred = deferred_end(tmp_path)
    store = WorkStore(root).directory
    store.chmod(0o555)
    try:
        ended = settle(deferred, present(DAEMON))
    finally:
        store.chmod(0o755)

    assert ended == []
    assert WorkStore(root).active()[0] == [work]


# --- Recovery and late ends --------------------------------------------------


def test_a_settler_that_never_ran_leaves_the_run_recoverable(tmp_path: Path) -> None:
    root, work, _deferred = deferred_end(tmp_path)
    after = table_lookup({REPLACEMENT.pid: REPLACEMENT})
    (orphan,) = runs(root, after)
    assert orphan.orphaned

    # The restarted daemon reloads the thread; the agent opts in again.
    recovered = bind(root, CODEX_SESSION, REPLACEMENT, "build-observer")

    assert recovered.issue_id == work.issue_id
    assert recovered.session_process == SessionProcess(
        pid=REPLACEMENT.pid, started_at=REPLACEMENT.started_at
    )
    (run,) = runs(root, after)
    assert not run.orphaned


@pytest.mark.parametrize("moved", [False, True], ids=["in-place", "other-worktree"])
def test_a_reloaded_thread_is_listed_unbound_beside_its_orphan(
    tmp_path: Path, moved: bool
) -> None:
    a, b = two_worktrees(tmp_path)
    work = bind(a, CODEX_SESSION, DAEMON, "build-observer")
    settlers = Settlers()
    session_end(a, CODEX_SESSION, DAEMON, settlers)
    after = table_lookup({REPLACEMENT.pid: REPLACEMENT})
    (deferred,) = settlers.started
    settle(deferred, after)

    # The replacement reloaded the thread with no SessionStart; its next turn
    # publishes from the new Host Process, which neither continues nor carries.
    publication = publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b if moved else a),
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "turn-after-restart",
        },
        process=REPLACEMENT,
        harness="codex",
        lookup=after,
    )

    assert (publication.work, publication.continued) == ("unchanged", None)
    assert WorkStore(a).active()[0] == [work]
    observed, _diagnostics = observe_agent_runs(
        {"project:example": [target(a), target(b)]},
        Path("/nonexistent-global-store"),
        lookup=after,
    )
    assert sorted(
        (run.issue_id or "", run.orphaned, run.last_activity_at is None)
        for run in observed
    ) == [("", False, False), (work.issue_id, True, True)]


def test_a_late_end_from_the_replacement_leaves_the_orphan(tmp_path: Path) -> None:
    root, work, deferred = deferred_end(tmp_path)
    settle(deferred, absent())
    # The replacement reloaded the thread silently, then unloads or stops.
    hook_record(root, CODEX_SESSION, "codex", REPLACEMENT)
    settlers = Settlers()

    publication = session_end(root, CODEX_SESSION, REPLACEMENT, settlers)

    assert publication.work == "unchanged"
    assert settlers.started == []
    assert WorkStore(root).active()[0] == [work]


def test_a_late_end_from_the_old_daemon_leaves_the_recovered_run(
    tmp_path: Path,
) -> None:
    root, _work, _deferred = deferred_end(tmp_path)
    recovered = bind(root, CODEX_SESSION, REPLACEMENT, "build-observer")
    settlers = Settlers()

    publication = session_end(root, CODEX_SESSION, DAEMON, settlers)

    assert publication.work == "unchanged"
    assert settlers.started == []
    assert WorkStore(root).active()[0] == [recovered]


def test_every_bound_thread_of_a_stopped_daemon_is_orphaned(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    first = bind(a, CODEX_SESSION, DAEMON, "build-observer")
    second = bind(b, SIBLING, DAEMON, "fix-crash")
    hook_record(a, UNBOUND, "codex", DAEMON)
    settlers = Settlers()

    # A stop runs every loaded thread's SessionEnd at once.
    works = [
        session_end(a, CODEX_SESSION, DAEMON, settlers).work,
        session_end(b, SIBLING, DAEMON, settlers).work,
        session_end(a, UNBOUND, DAEMON, settlers).work,
    ]

    assert works == ["deferred", "deferred", "unchanged"]
    assert [deferred.session_id for deferred in settlers.started] == [
        CODEX_SESSION,
        SIBLING,
    ]
    assert [settle(deferred, absent()) for deferred in settlers.started] == [[], []]
    assert WorkStore(a).active()[0] == [first]
    assert WorkStore(b).active()[0] == [second]
    assert sorted((run.issue_id, run.orphaned) for run in runs(a, absent(), b)) == [
        (second.issue_id, True),
        (first.issue_id, True),
    ]


def test_an_unloaded_thread_ends_while_its_sibling_stays_bound(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo").resolve()
    bind(root, CODEX_SESSION, DAEMON, "build-observer")
    sibling = bind(root, SIBLING, DAEMON, "fix-crash")
    settlers = Settlers()
    session_end(root, CODEX_SESSION, DAEMON, settlers)

    (deferred,) = settlers.started
    settle(deferred, present(DAEMON))

    assert WorkStore(root).active()[0] == [sibling]
    (run,) = runs(root, present(DAEMON))
    assert (run.issue_id, run.orphaned) == (sibling.issue_id, False)


# --- Starting the settler and its Event Log ----------------------------------


def test_the_settler_starts_detached_from_the_hook(tmp_path: Path) -> None:
    _root, _work, deferred = deferred_end(tmp_path)
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def popen(command: list[str], **options: Any) -> None:
        calls.append((command, options))

    spawn_settler(deferred, popen=popen)

    ((command, options),) = calls
    assert command == settler_command(deferred)
    assert command[:5] == [sys.executable, "-P", "-m", "dashpot.hook", "settle"]
    assert DeferredEnd.parse(command[5]) == deferred
    assert options == {
        "cwd": "/",
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "start_new_session": True,
    }


def test_the_settlers_interpreter_never_imports_from_the_session_directory(
    tmp_path: Path,
) -> None:
    # A Project with a top-level module named like one the settler imports
    # must neither break it nor run inside it.
    _root, _work, deferred = deferred_end(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "json.py").write_text("raise SystemExit('shadowed json')\n")
    command = settler_command(deferred)
    interpreter = command[: command.index("-m")]
    result = subprocess.run(
        [*interpreter, "-c", "import json; print(json.__name__)"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode, result.stdout.strip()) == (0, "json")


def written(directory: Path) -> list[dict[str, Any]]:
    """Every Event Log record written under ``directory``, file by file."""
    return [
        json.loads(line)
        for path in sorted(directory.glob("*.jsonl"))
        for line in path.read_bytes().splitlines()
    ]


@pytest.mark.parametrize(
    ("lookup", "change", "issue"),
    [
        pytest.param(present(DAEMON), "ended", True, id="unloaded"),
        pytest.param(absent(), "unchanged", False, id="stopped"),
    ],
)
def test_the_settler_records_its_outcome_as_the_session_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lookup: ProcessLookup,
    change: str,
    issue: bool,
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    _root, work, deferred = deferred_end(tmp_path)
    events = tmp_path / "events"
    clock = Clock()

    code = hook.settle_main(
        [deferred.wire()],
        event_log=EventLogDestination(events),
        lookup=lookup,
        clock=clock,
        sleep=clock.sleep,
    )

    assert code == 0
    start, outcome, end = written(events)
    assert start["dashpot.process.kind"] == "hook:codex:SessionEnd"
    assert start["dashpot.agent_session.id"] == CODEX_SESSION
    assert outcome["dashpot.hook.event"] == "SessionEnd"
    assert outcome["dashpot.outcome.result"] == "succeeded"
    assert outcome["dashpot.agent_session.state"] == "ended"
    assert outcome["dashpot.work_store.change"] == change
    assert outcome.get("dashpot.issue.id") == (work.issue_id if issue else None)
    assert end["process.exit.code"] == 0


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        pytest.param([], "ValueError", id="missing"),
        pytest.param(["{"], "ValidationError", id="unreadable"),
    ],
)
def test_a_settler_without_a_readable_end_records_its_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str], error: str
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    monkeypatch.chdir(tmp_path)
    events = tmp_path / "events"

    assert hook.settle_main(argv, event_log=EventLogDestination(events)) == 1

    start, outcome, end = written(events)
    assert start["dashpot.process.kind"] == "hook:codex:SessionEnd"
    assert outcome["dashpot.outcome.result"] == "failed"
    assert outcome["error.type"] == error
    assert end["process.exit.code"] == 1


def test_the_hook_module_runs_a_settler_to_its_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The settler command, run in the foreground: its daemon, a pid with
    # another start time, reads as gone at once, so the run is left orphaned.
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    root, work, deferred = deferred_end(tmp_path)
    destination = route_event_log(root)
    assert destination is not None

    ran = subprocess.run(
        settler_command(deferred),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "", "")
    assert WorkStore(root).active()[0] == [work]
    (outcome,) = (
        event
        for event in written(destination.directory)
        if event.get("event.name") == "hook.outcome"
    )
    assert outcome["dashpot.process.kind"] == "hook:codex:SessionEnd"
    assert outcome["dashpot.work_store.change"] == "unchanged"


def test_the_hook_module_publishes_a_codex_event_without_a_command(
    tmp_path: Path,
) -> None:
    ran = subprocess.run(
        [sys.executable, "-m", "dashpot.hook"],
        cwd=tmp_path,
        input="{",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert ran.returncode == 1
    assert ran.stderr.startswith("dashpot Codex hook: ")


def test_the_hook_module_reads_only_a_leading_settle_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[str] = []

    def publish() -> int:
        ran.append("publish")
        return 3

    def settle(argv: Sequence[str]) -> int:
        ran.append(f"settle {list(argv)}")
        return 4

    monkeypatch.setattr(hook, "main", publish)
    monkeypatch.setattr(hook, "settle_main", settle)

    assert hook.module_main(["other", "settle"]) == 3
    assert hook.module_main([]) == 3
    assert hook.module_main(["settle", "{}"]) == 4
    assert ran == ["publish", "publish", "settle ['{}']"]
