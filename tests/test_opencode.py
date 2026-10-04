"""OpenCode v2 sessions through the shared runtime model (ADR 0090).

Each scenario follows what the #393 and #405 experiments measured at
OpenCode 2.0.22 (``scripts/experiments/opencode-393`` and ``-405``): one
server runs the plugin's helper and every shell as its direct children,
every session event carries the session's durable sequence, a child
session names its ``parentID`` and a fork names none, and a move keeps a
session's identity and server. The plugin's requests are driven through
``publish_opencode`` with a fake process lookup.
"""

from __future__ import annotations

import functools
import io
import json
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from dashpot import hook
from dashpot.core.event_log import EventLogDestination
from dashpot.core.model import Diagnostic
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions import integrate
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_records import (
    project_session_store,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import (
    reachable_hook_stores,
    sessions_with_live_subagents,
)
from dashpot.sessions.integrate import integration_status
from dashpot.sessions.opencode_publish import (
    OpenCodeOutcome,
    parse_request,
    publish_opencode,
)
from dashpot.sessions.opencode_publishers import PublisherStore
from dashpot.sessions.processes import (
    ProcessAbsent,
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
)
from dashpot.sessions.work import (
    IssueWorkError,
    show_issue_work,
    start_issue_work,
    stop_issue_work,
)
from dashpot.sessions.work_store import WorkStore
from factories import CLAUDE, CODEX, hook_record, hook_record_document
from helpers import table_lookup, unobservable
from test_event_logs import written
from test_work import (
    CLAUDE_ENVIRON,
    CODEX_ENVIRON,
    linked_worktree,
    repository,
    target,
)

SHELL_PID = 10
SERVER = ProcessIdentity(
    4100,
    1,
    "opencode",
    "Thu Oct 01 09:00:00 2026",
    "/home/person/.opencode/bin/opencode serve --service",
)
# The same sessions' server after a TUI of another release replaced it.
REPLACEMENT = ProcessIdentity(
    4300, 1, "opencode", "Thu Oct 01 10:00:00 2026", SERVER.arguments
)
ROOT = "ses_f05e57dcaffegJ87K4r5rjvjSs"
CHILD = "ses_f05e56ef6ffevvmI30laCCAoGe"
FORK = "ses_f05e56a73ffeklp3IYeT79oPjQ"
GENERATION = "d7e54b7b-45ab-41b5-9501-898464014ae4"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


@pytest.fixture
def below(monkeypatch: pytest.MonkeyPatch) -> Callable[..., ProcessLookup]:
    """Build a lookup whose ancestry walk meets ``hosts`` above a shell, nearest first.

    The helper and every shell are direct children of the server; every PID
    not named is gone.
    """
    monkeypatch.setattr("dashpot.sessions.processes.os.getppid", lambda: SHELL_PID)

    def lookup(*hosts: ProcessIdentity) -> ProcessLookup:
        chain: list[ProcessIdentity] = []
        for host, above in zip(hosts, (*hosts[1:], None), strict=True):
            chain.append(
                ProcessIdentity(
                    host.pid,
                    above.pid if above is not None else 1,
                    host.command,
                    host.started_at,
                    host.arguments,
                )
            )
        shell = ProcessIdentity(SHELL_PID, hosts[0].pid, "bash", hosts[0].started_at)
        return table_lookup({process.pid: process for process in (shell, *chain)})

    return lookup


class Server:
    """One OpenCode server's plugin registry, as its helper receives requests.

    Each session's events carry the next durable sequence unless a test names
    one, as OpenCode's own envelope does.
    """

    def __init__(self, lookup: ProcessLookup, host: ProcessIdentity = SERVER) -> None:
        self.lookup = lookup
        self.host = host
        self.sequences: dict[str, int] = {}
        self.events = 0

    def send(self, kind: str, **fields: Any) -> OpenCodeOutcome:
        wire = {
            "protocol": 2,
            "kind": kind,
            "generation": GENERATION,
            "pid": self.host.pid,
            "deadlineMs": 3000,
            **fields,
        }
        return publish_opencode(parse_request(json.dumps(wire)), self.lookup)

    def register(self, location: Path) -> dict[str, Any]:
        return answer(self.send("register", location=str(location)))

    def event(
        self,
        kind: str,
        at: Path,
        session: str = ROOT,
        *,
        root: str | None = None,
        sequence: int | None = None,
        reason: str | None = None,
        to: Path | None = None,
    ) -> OpenCodeOutcome:
        if sequence is None:
            sequence = self.sequences.get(session, -1) + 1
        self.sequences[session] = max(sequence, self.sequences.get(session, -1))
        self.events += 1
        event: dict[str, Any] = {
            "id": f"evt_{self.events:04d}",
            "type": f"session.{kind}",
            "sequence": sequence,
        }
        if reason is not None:
            event["reason"] = reason
        if to is not None:
            event["to"] = str(to)
        return self.send(
            "event",
            session={"id": session, "root": root or session, "location": str(at)},
            event=event,
        )

    def turn(self, at: Path, session: str = ROOT, **options: Any) -> str:
        return self.event("execution.started", at, session, **options).result

    def finish(self, at: Path, session: str = ROOT, **options: Any) -> str:
        return self.event("execution.succeeded", at, session, **options).result

    def gone(self, at: Path, session: str = ROOT, root: str | None = None) -> str:
        return self.send(
            "gone",
            session={"id": session, "root": root or session, "location": str(at)},
        ).result

    def unobserved(self, *locations: Path) -> str:
        return self.send(
            "unobserved", locations=[str(location) for location in locations]
        ).result

    def claim(self, session: str = ROOT) -> dict[str, str]:
        """The environment OpenCode and the plugin give a model's shell."""
        return {
            "OPENCODE_SESSION_ID": session,
            "OPENCODE": "1",
            "DASHPOT_OPENCODE_PID": str(self.host.pid),
        }


def answer(outcome: OpenCodeOutcome) -> dict[str, Any]:
    """The acknowledgment as the plugin reads it from the helper's stdout."""
    return json.loads(outcome.acknowledgment.wire())


def record(at: Path, session: str = ROOT) -> dict[str, Any] | None:
    """The session's hook record in the Project-local store, if there is one."""
    path = session_directory(at) / f"{session}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def observed(
    at: Path, lookup: ProcessLookup, *others: Path
) -> tuple[list[Any], list[Diagnostic]]:
    """Observe the Project at ``at``, beside a Project at each of ``others``."""
    targets = {"project:test": [target(at)]}
    targets.update({f"project:{path.name}": [target(path)] for path in others})
    return observe_agent_runs(targets, state_directory(), lookup=lookup)


def runs(at: Path, lookup: ProcessLookup) -> list[Any]:
    return observed(at, lookup)[0]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return repository(tmp_path / "repo").resolve()


@pytest.fixture
def server(below: Callable[..., ProcessLookup]) -> Server:
    return Server(below(SERVER))


# --- The Host Process and the request -----------------------------------------


def test_a_helper_that_is_not_the_servers_child_publishes_nothing(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    elsewhere = Server(below(CODEX), host=SERVER)
    impostor = Server(below(SERVER), host=REPLACEMENT)

    assert answer(elsewhere.event("created", project)) == {
        "result": "rejected",
        "reason": "host-process-not-found",
    }
    assert answer(impostor.event("created", project)) == {
        "result": "rejected",
        "reason": "host-process-not-corroborated",
    }
    assert record(project) is None


def test_a_server_the_npm_install_names_opencode_exe_is_the_host_process(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    npm = ProcessIdentity(
        4400, 1, "/usr/lib/node_modules/opencode/bin/opencode.exe", "now", "serve"
    )

    assert Server(below(npm), host=npm).turn(project) == "accepted"


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"protocol": 1}, id="protocol-1"),
        pytest.param({"kind": "register"}, id="register-without-location"),
        pytest.param({"kind": "gone"}, id="gone-without-session"),
        pytest.param(
            {"kind": "event", "session": {"id": ROOT, "root": ROOT, "location": "/"}},
            id="event-without-event",
        ),
        pytest.param(
            {
                "kind": "event",
                "session": {"id": ROOT, "root": ROOT, "location": "/"},
                "event": {"id": "evt_1", "type": "session.moved", "sequence": 1},
            },
            id="move-without-destination",
        ),
        pytest.param(
            {
                "kind": "event",
                "session": {"id": ROOT, "root": ROOT, "location": "/"},
                "event": {
                    "id": "evt_1",
                    "type": "session.created",
                    "sequence": 1,
                    "to": "/",
                },
            },
            id="destination-without-move",
        ),
        pytest.param(
            {
                "kind": "event",
                "session": {"id": ROOT, "root": ROOT, "location": "/"},
                "event": {"id": "evt_1", "type": "session.status", "sequence": 1},
            },
            id="v1-status",
        ),
    ],
)
def test_a_malformed_plugin_request_is_refused(fields: dict[str, Any]) -> None:
    wire = {
        "protocol": 2,
        "kind": "unobserved",
        "generation": GENERATION,
        "pid": SERVER.pid,
        "deadlineMs": 3000,
        **fields,
    }

    with pytest.raises(ValueError, match="OpenCode plugin request"):
        parse_request(json.dumps(wire))


# --- A root session's activity ----------------------------------------------


def test_a_root_sessions_executions_are_its_turns(
    project: Path, server: Server
) -> None:
    created = server.event("created", project)
    assert created.written == ("SessionStart",)

    assert server.turn(project) == "accepted"
    running = record(project)
    assert running is not None
    assert (running["harness"], running["state"], running["event"]) == (
        "opencode",
        "running",
        "UserPromptSubmit",
    )
    assert running["sessionProcess"]["pid"] == SERVER.pid

    assert server.finish(project) == "accepted"
    waiting = record(project)
    assert waiting is not None
    assert (waiting["state"], waiting["event"]) == ("waiting", "Stop")


@pytest.mark.parametrize("ending", ["failed", "interrupted"])
def test_an_execution_ending_any_way_reads_waiting(
    project: Path, server: Server, ending: str
) -> None:
    server.turn(project)

    ended = server.event(f"execution.{ending}", project, reason="inactivity")

    assert ended.written == ("Stop",)
    # OpenCode's reason is kept for the Event Log, not read as an outcome.
    assert answer(ended) == {"result": "accepted", "reason": "inactivity"}
    waiting = record(project)
    assert waiting is not None
    assert waiting["state"] == "waiting"


def test_a_publication_at_or_below_the_sessions_sequence_writes_nothing(
    project: Path, server: Server
) -> None:
    server.turn(project, sequence=4)
    server.finish(project, sequence=5)
    settled = record(project)

    assert server.finish(project, sequence=5) == "stale"
    assert server.turn(project, sequence=3) == "stale"
    assert record(project) == settled
    assert server.turn(project, sequence=6) == "accepted"


def test_a_sessions_first_publication_in_a_store_begins_its_incarnation(
    project: Path, server: Server
) -> None:
    # Its creation reached no instance, as before a plugin was installed.
    started = server.event("execution.started", project)

    assert started.written == ("SessionStart", "UserPromptSubmit")
    assert server.finish(project) == "accepted"
    again = server.event("execution.started", project)
    assert again.written == ("UserPromptSubmit",)


def test_a_deleted_session_ends_its_record_and_its_run(
    project: Path, server: Server
) -> None:
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    deleted = server.event("deleted", project)

    assert deleted.written == ("SessionEnd",)
    assert deleted.publications[-1].work == "ended"
    assert record(project) is None
    assert WorkStore(project).active()[0] == []
    # A stray start after the deletion of a running session revives nothing.
    assert answer(server.event("execution.started", project)) == {
        "result": "refused",
        "reason": "session-deleted",
    }
    assert record(project) is None


@pytest.mark.parametrize("configured", [False, True])
def test_a_location_outside_every_project_is_not_published(
    tmp_path: Path, server: Server, configured: bool
) -> None:
    scratch = (tmp_path / "scratch").resolve()
    scratch.mkdir()
    if configured:
        # A Git checkout, but not a configured Project.
        scratch = repository(tmp_path / "plain-git").resolve()
        (scratch / ".dashpot" / "config.json").unlink()

    assert answer(server.event("execution.started", scratch)) == {
        "result": "refused",
        "reason": "outside-project",
    }
    assert not state_directory().exists() or not any(state_directory().iterdir())


def test_a_location_that_no_longer_exists_is_not_published(
    tmp_path: Path, server: Server
) -> None:
    assert answer(server.event("execution.started", tmp_path / "removed")) == {
        "result": "refused",
        "reason": "outside-project",
    }


def test_a_session_resumed_by_another_server_begins_an_incarnation_there(
    project: Path, server: Server, below: Callable[..., ProcessLookup]
) -> None:
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    # A TUI of another release replaced the service, which resumes its sessions.
    replacement = Server(below(REPLACEMENT), host=REPLACEMENT)
    replacement.sequences = dict(server.sequences)
    resumed = replacement.event("execution.started", project)

    assert resumed.written == ("SessionStart", "UserPromptSubmit")
    assert all(item.work == "unchanged" for item in resumed.publications)
    (orphaned,) = [run for run in runs(project, replacement.lookup) if run.issue_id]
    assert orphaned.orphaned is True
    start_issue_work(
        project,
        "build-observer",
        lookup=replacement.lookup,
        environ=replacement.claim(),
    )
    (held,) = WorkStore(project).active()[0]
    assert held.session_process is not None
    assert held.session_process.pid == REPLACEMENT.pid


# --- Delegated work ---------------------------------------------------------


def test_a_child_session_is_a_sub_agent_of_its_root(
    project: Path, server: Server
) -> None:
    server.turn(project)
    assert server.event("created", project, CHILD, root=ROOT).written == ()
    server.turn(project, CHILD, root=ROOT)
    # A background child keeps working after its root's execution succeeded.
    server.finish(project)

    working = record(project)
    assert working is not None
    assert record(project, CHILD) is None
    assert (working["liveSubagents"], working["state"]) == ([CHILD], "running")

    assert server.finish(project, CHILD, root=ROOT) == "accepted"
    settled = record(project)
    assert settled is not None
    assert (settled["liveSubagents"], settled["state"]) == ([], "waiting")


def test_a_deleted_child_stops_on_its_root(project: Path, server: Server) -> None:
    server.turn(project)
    server.turn(project, CHILD, root=ROOT)

    assert server.event("deleted", project, CHILD, root=ROOT).written == (
        "SubagentStop",
    )

    settled = record(project)
    assert settled is not None
    assert settled["liveSubagents"] == []
    assert answer(server.event("execution.started", project, CHILD, root=ROOT)) == {
        "result": "refused",
        "reason": "session-deleted",
    }


def test_a_grandchild_is_a_sub_agent_of_the_root(project: Path, server: Server) -> None:
    server.turn(project)

    server.turn(project, FORK, root=ROOT)

    working = record(project)
    assert working is not None
    assert working["liveSubagents"] == [FORK]


def test_a_childs_first_word_starts_its_roots_record(
    project: Path, server: Server
) -> None:
    started = server.event("execution.started", project, CHILD, root=ROOT)

    assert started.written == ("SessionStart", "SubagentStart")
    working = record(project)
    assert working is not None
    assert (working["state"], working["liveSubagents"]) == ("running", [CHILD])


def test_a_child_stop_with_no_root_record_writes_nothing(
    project: Path, server: Server
) -> None:
    server.finish(project, CHILD, root=ROOT)

    assert record(project) is None


def test_a_fork_is_a_root_of_its_own_and_inherits_no_run(
    project: Path, server: Server
) -> None:
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    assert server.event("forked", project, FORK).written == ("SessionStart",)
    server.turn(project, FORK)

    forked = record(project, FORK)
    assert forked is not None
    assert forked["liveSubagents"] == []
    bound = {run.session_id: run.issue_id for run in runs(project, server.lookup)}
    assert bound == {ROOT: "I_observer", FORK: None}


# --- Moves ------------------------------------------------------------------


def test_a_move_within_its_repository_carries_its_run(
    tmp_path: Path, project: Path, server: Server
) -> None:
    linked = linked_worktree(project, tmp_path / "linked", "linked").resolve()
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    moved = server.event("moved", project, to=linked)

    assert moved.written == ("SessionMoved",)
    assert moved.publications[-1].work == "relocated"
    arrived = record(linked)
    assert arrived is not None
    assert (arrived["cwd"], arrived["state"]) == (str(linked), "running")
    assert WorkStore(project).active()[0] == []
    (held,) = WorkStore(linked).active()[0]
    assert held.issue_id == "I_observer"
    # Its later events are written where it now is, beginning nothing.
    assert server.finish(linked) == "accepted"
    assert server.event("execution.started", linked).written == ("UserPromptSubmit",)


def test_a_childs_move_writes_nothing(
    tmp_path: Path, project: Path, server: Server
) -> None:
    linked = linked_worktree(project, tmp_path / "linked", "linked").resolve()
    server.turn(project)

    assert server.event("moved", project, CHILD, root=ROOT, to=linked).written == ()
    assert record(linked) is None


def test_a_moved_roots_worker_holds_the_repository_until_it_ends_and_then_none(
    tmp_path: Path, project: Path, server: Server
) -> None:
    # #421's order at OpenCode 2.0.22: the bound root launches a background
    # child and its execution ends; the root is moved while the child runs;
    # the child ends where it was created, and its notice wakes the root at
    # the Worktree it moved to.
    linked = linked_worktree(project, tmp_path / "linked", "linked").resolve()
    spare = (tmp_path / "spare").resolve()
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "spare", str(spare)],
        cwd=project,
        check=True,
    )
    worktrees = [project, linked, spare]
    stores = reachable_hook_stores(worktrees)
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )
    server.turn(project, CHILD, root=ROOT)
    server.finish(project)
    assert server.event("moved", project, to=linked).written == ("SessionMoved",)

    def sub_agent_obstacles() -> list[str]:
        return [
            blocker.detail
            for blocker in assess_worktree_occupancy(spare, worktrees, server.lookup)
            if blocker.kind == "sub-agent"
        ]

    def shown() -> list[str]:
        return [
            line
            for line in show_issue_work(linked, lookup=server.lookup)
            if "listed as working" in line
        ]

    # While the child works, the root holds it wherever it moved.
    (delegating,) = sessions_with_live_subagents(worktrees, stores, server.lookup)
    assert (delegating.worktree, delegating.record.live_subagents) == (
        linked,
        (CHILD,),
    )
    (blocked,) = sub_agent_obstacles()
    assert f"at {linked} has 1 sub-agent listed as working ({CHILD};" in blocked
    (working,) = shown()
    assert f"has 1 sub-agent listed as working ({CHILD})" in working

    assert server.finish(project, CHILD, root=ROOT) == "accepted"
    server.turn(linked)
    server.finish(linked)

    left, arrived = record(project), record(linked)
    assert left is not None
    assert arrived is not None
    assert (arrived["state"], arrived["event"], arrived["liveSubagents"]) == (
        "waiting",
        "Stop",
        [],
    )
    assert left["liveSubagents"] == []
    assert sessions_with_live_subagents(worktrees, stores, server.lookup) == []
    assert sub_agent_obstacles() == []
    assert shown() == []


def test_a_move_to_another_repository_leaves_its_run_behind(
    tmp_path: Path, project: Path, server: Server
) -> None:
    other = repository(tmp_path / "other").resolve()
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    moved = server.event("moved", project, to=other)

    assert moved.written == ("SessionMoved",)
    # Written where the session was, naming where it went.
    left = record(project)
    assert left is not None
    assert left["cwd"] == str(other)
    (held,) = WorkStore(project).active()[0]
    assert held.issue_id == "I_observer"
    _runs, diagnostics = observed(project, server.lookup, other)
    assert [item.code for item in diagnostics] == ["work-session-elsewhere"]
    # Its next event begins an incarnation in the other Repository.
    assert server.finish(other) == "accepted"
    arrived = record(other)
    assert arrived is not None
    assert arrived["lastSessionStartAt"] is not None


def test_a_move_outside_every_project_is_written_where_it_left(
    tmp_path: Path, project: Path, server: Server
) -> None:
    plain = (tmp_path / "plain").resolve()
    plain.mkdir()
    server.turn(project)

    assert server.event("moved", project, to=plain).written == ("SessionMoved",)

    left = record(project)
    assert left is not None
    assert left["cwd"] == str(plain)
    assert answer(server.event("execution.succeeded", plain)) == {
        "result": "refused",
        "reason": "outside-project",
    }
    # Nor is a move from there into a Project written, until its next event.
    assert server.event("moved", plain, to=project).result == "refused"


# --- The Host Process's last instance ---------------------------------------


def test_a_server_with_no_live_instance_marks_its_running_roots_unknown(
    project: Path, server: Server, below: Callable[..., ProcessLookup]
) -> None:
    server.turn(project)
    server.turn(project, FORK)
    server.finish(project, FORK)
    server.turn(project, "ses_holding")
    server.turn(project, CHILD, root="ses_holding")
    server.finish(project, "ses_holding")
    other = Server(below(REPLACEMENT), host=REPLACEMENT)
    other.turn(project, "ses_elsewhere")

    assert server.unobserved(project, project) == "accepted"

    # Another server's session is not this one's to mark.
    elsewhere = record(project, "ses_elsewhere")
    assert elsewhere is not None
    assert elsewhere["sessionProcessUnobservable"] is None

    states = {run.session_id: run.state for run in runs(project, server.lookup)}
    assert states == {
        ROOT: "unknown",
        FORK: "waiting",
        "ses_holding": "unknown",
    }
    marked = record(project)
    assert marked is not None
    assert marked["sessionProcess"]["pid"] == SERVER.pid
    assert marked["sessionProcessUnobservable"] == "opencode-no-live-instance"


def test_any_publication_clears_the_mark_and_forgets_its_sub_agents(
    project: Path, server: Server
) -> None:
    server.turn(project)
    server.turn(project, CHILD, root=ROOT)
    server.unobserved(project)

    # The child's end reached no instance; the root's next event arrives.
    assert server.finish(project) == "accepted"

    observed_again = record(project)
    assert observed_again is not None
    assert observed_again["sessionProcessUnobservable"] is None
    assert (observed_again["state"], observed_again["liveSubagents"]) == (
        "waiting",
        [],
    )
    # A live child's next event adds it again.
    server.turn(project, CHILD, root=ROOT)
    working = record(project)
    assert working is not None
    assert working["liveSubagents"] == [CHILD]


def test_a_marked_session_reads_gone_once_its_server_exits(
    project: Path, server: Server
) -> None:
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )
    server.unobserved(project)

    (live,) = runs(project, server.lookup)
    assert (live.state, live.orphaned) == ("unknown", False)
    (exited,) = runs(project, table_lookup({}))
    assert (exited.issue_id, exited.orphaned) == ("I_observer", True)


def test_a_marked_session_stays_unknown_while_its_server_is_unobservable(
    project: Path, server: Server
) -> None:
    server.turn(project)
    server.unobserved(project)

    (seen,) = runs(project, unobservable("ps-timeout"))

    assert (seen.session_id, seen.state) == (ROOT, "unknown")


@pytest.mark.parametrize("claude_ended", [False, True])
def test_the_mark_finds_its_record_beside_another_harness_of_the_same_id(
    project: Path, server: Server, claude_ended: bool
) -> None:
    # Claude Code took the session's plain name first, so OpenCode's record
    # is kept under its harness-scoped one, even once Claude Code's is gone.
    claude = hook_record(project, ROOT, "claude-code", CLAUDE)
    server.turn(project)
    if claude_ended:
        project_session_store(project).write(
            hook_record_document(project, ROOT, "claude-code", CLAUDE, state="ended")
        )

    server.unobserved(project)

    if claude_ended:
        assert not claude.exists()
    else:
        kept = json.loads(claude.read_text())
        assert (kept["harness"], kept["sessionProcess"]["pid"]) == (
            "claude-code",
            CLAUDE.pid,
        )
    (marked,) = [
        json.loads(path.read_text())
        for path in session_directory(project).glob("opencode-session-*.json")
    ]
    assert marked["sessionProcessUnobservable"] == "opencode-no-live-instance"


def test_the_mark_skips_locations_outside_every_project(
    tmp_path: Path, server: Server
) -> None:
    assert server.unobserved(tmp_path) == "accepted"


# --- Recovery on registration -----------------------------------------------


def test_registration_returns_the_roots_its_store_records_on_its_server(
    project: Path, server: Server, below: Callable[..., ProcessLookup]
) -> None:
    server.turn(project)
    server.turn(project, CHILD, root=ROOT)
    server.turn(project, FORK)
    Server(below(REPLACEMENT), host=REPLACEMENT).turn(project, "ses_elsewhere")

    recovered = server.register(project)

    assert recovered == {
        "result": "accepted",
        "sessions": sorted(
            [{"id": ROOT, "subagents": [CHILD]}, {"id": FORK, "subagents": []}],
            key=lambda session: session["id"],
        ),
    }


def test_registration_skips_an_unreadable_record(project: Path, server: Server) -> None:
    server.turn(project)
    (session_directory(project) / "torn.json").write_text("{not json")

    assert server.register(project) == {
        "result": "accepted",
        "sessions": [{"id": ROOT, "subagents": []}],
    }


def test_registration_outside_every_project_recovers_nothing(
    tmp_path: Path, server: Server
) -> None:
    assert server.register(tmp_path) == {"result": "accepted", "sessions": []}


def test_a_recovered_deletion_ends_the_session_and_its_run(
    project: Path, server: Server
) -> None:
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    assert server.gone(project) == "accepted"

    assert record(project) is None
    assert WorkStore(project).active()[0] == []
    assert server.turn(project) == "refused"


def test_a_recovered_childs_deletion_stops_it_on_its_root(
    project: Path, server: Server
) -> None:
    server.turn(project)
    server.turn(project, CHILD, root=ROOT)

    assert server.gone(project, CHILD, root=ROOT) == "accepted"

    settled = record(project)
    assert settled is not None
    assert settled["liveSubagents"] == []


def test_an_unreadable_publisher_record_accepts_the_next_publication(
    project: Path, server: Server
) -> None:
    server.turn(project, sequence=7)
    store = PublisherStore(session_directory(project))
    store.record_path("publisher").write_text("{not json")

    assert server.finish(project, sequence=2) == "accepted"


# --- Issue work ---------------------------------------------------------------


def test_a_model_shells_claim_opts_its_session_in(
    project: Path, server: Server
) -> None:
    server.turn(project)

    messages = start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    assert "started work on build-observer" in messages[0]
    (held,) = WorkStore(project).active()[0]
    assert held.issue_id == "I_observer"
    assert held.session_process is not None
    assert held.session_process.pid == SERVER.pid


def test_a_marked_sessions_claim_still_opts_in(project: Path, server: Server) -> None:
    server.turn(project)
    server.unobserved(project)

    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )

    (held,) = WorkStore(project).active()[0]
    assert held.issue_id == "I_observer"


def test_a_child_sessions_claim_is_refused_as_delegated(
    project: Path, server: Server
) -> None:
    server.turn(project)
    server.turn(project, CHILD, root=ROOT)

    with pytest.raises(IssueWorkError, match=f"delegated-session.*{ROOT}"):
        start_issue_work(
            project,
            "build-observer",
            lookup=server.lookup,
            environ=server.claim(CHILD),
        )

    assert WorkStore(project).active()[0] == []


def test_a_deleted_sessions_claim_is_refused(project: Path, server: Server) -> None:
    server.turn(project)
    server.event("deleted", project)

    with pytest.raises(IssueWorkError, match="OpenCode has deleted the session"):
        start_issue_work(
            project, "build-observer", lookup=server.lookup, environ=server.claim()
        )


def test_an_explicit_override_cannot_name_an_opencode_session(
    project: Path, server: Server
) -> None:
    server.turn(project)

    with pytest.raises(IssueWorkError, match="is not OpenCode's own claim"):
        start_issue_work(
            project,
            "build-observer",
            lookup=server.lookup,
            environ={"DASHPOT_AGENT_SESSION": f"opencode:{ROOT}"},
        )


def test_a_claim_naming_another_server_is_refused(
    project: Path, server: Server
) -> None:
    server.turn(project)
    # Variables a shell inherited from another server's shell.
    environ = {**server.claim(), "DASHPOT_OPENCODE_PID": str(REPLACEMENT.pid)}

    with pytest.raises(IssueWorkError, match="attributes the harness to pid 4300"):
        start_issue_work(
            project, "build-observer", lookup=server.lookup, environ=environ
        )


def test_a_user_shell_is_told_only_an_agents_command_opts_in(
    project: Path, server: Server
) -> None:
    server.turn(project)

    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(
            project,
            "build-observer",
            lookup=server.lookup,
            environ={"DASHPOT_OPENCODE_PID": str(SERVER.pid)},
        )

    message = str(refused.value)
    assert "running Codex, Claude Code, or OpenCode session" in message
    assert "a shell the user started in OpenCode" in message


def test_a_command_opencode_v1_ran_is_told_v1_is_refused(
    project: Path, server: Server
) -> None:
    # The plugin's v1 entry publishes nothing and sets the refusal on every
    # shell, which carries no claim: OpenCode v1 sets no session variable.
    environ = {"DASHPOT_OPENCODE_REFUSAL": "opencode-v1", "OPENCODE": "1"}

    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(
            project, "build-observer", lookup=server.lookup, environ=environ
        )

    message = str(refused.value)
    assert "running Codex, Claude Code, or OpenCode session" in message
    assert "runs in OpenCode v1, and Dashpot observes OpenCode v2 only" in message
    assert "OpenCode terminal" not in message


def test_a_terminal_is_told_it_is_no_agents_command(
    project: Path, server: Server
) -> None:
    server.turn(project)

    # A terminal runs no plugin hook, so it carries no claim at all.
    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(project, "build-observer", lookup=server.lookup, environ={})

    message = str(refused.value)
    assert "this command runs in an OpenCode terminal, which is no agent's" in message
    assert "has not loaded the plugin" not in message


def test_opencodes_variables_without_the_plugins_mark_name_both_causes(
    project: Path, server: Server
) -> None:
    server.turn(project)
    # A model's shell on a server without the plugin carries OpenCode's own
    # variables, as a terminal that inherited them does.
    environ = {"OPENCODE_SESSION_ID": ROOT, "OPENCODE": "1"}

    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(
            project, "build-observer", lookup=server.lookup, environ=environ
        )

    message = str(refused.value)
    assert "carries OpenCode's session variables but not the mark" in message
    assert "has not loaded the plugin" in message
    assert (
        "'dashpot integrate opencode --status', then run 'opencode reload'" in message
    )
    assert "or it runs in an OpenCode terminal" in message


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("OPENCODE_SESSION_ID", ""),
        ("OPENCODE", ""),
        ("OPENCODE", "true"),
        ("DASHPOT_OPENCODE_PID", "not-a-pid"),
    ],
)
def test_a_partial_claim_is_no_claim(
    project: Path, server: Server, variable: str, value: str
) -> None:
    server.turn(project)
    environ = {**server.claim(), variable: value}

    with pytest.raises(IssueWorkError, match="no supported agent session"):
        start_issue_work(
            project, "build-observer", lookup=server.lookup, environ=environ
        )


def test_an_opencode_server_alone_never_corroborates_another_harness(
    project: Path, server: Server
) -> None:
    """A command under OpenCode that inherited a Codex claim is refused.

    The plugin blanks every inherited claim; without the plugin, the nearest
    host is the OpenCode server, which the Codex claim cannot describe.
    """
    server.turn(project)
    hook_record(project, "019dd9a2-codex", "codex", CODEX)

    def lookup(pid: int) -> ProcessObservation:
        return ProcessPresent(CODEX) if pid == CODEX.pid else server.lookup(pid)

    with pytest.raises(IssueWorkError, match="does not corroborate"):
        start_issue_work(
            project,
            "build-observer",
            lookup=lookup,
            environ={"CODEX_THREAD_ID": "019dd9a2-codex"},
        )


@pytest.mark.parametrize(
    ("host", "environ", "harness"),
    [
        pytest.param(CLAUDE, CLAUDE_ENVIRON, "claude-code", id="claude-code"),
        pytest.param(CODEX, CODEX_ENVIRON, "codex", id="codex"),
    ],
)
def test_a_harness_launched_inside_opencode_identifies_its_own_session(
    project: Path,
    below: Callable[..., ProcessLookup],
    host: ProcessIdentity,
    environ: Mapping[str, str],
    harness: str,
) -> None:
    session = next(value for key, value in environ.items() if "PID" not in key)
    hook_record(project, session, harness, host)
    lookup = below(host, SERVER)

    start_issue_work(project, "build-observer", lookup=lookup, environ=environ)

    (held,) = WorkStore(project).active()[0]
    assert held.session_key.startswith(harness)
    assert held.session_process is not None
    assert held.session_process.pid == host.pid


def test_a_record_naming_no_host_process_corroborates_no_claim(
    project: Path, server: Server
) -> None:
    hook_record(project, ROOT, "opencode", None)

    with pytest.raises(IssueWorkError, match="names no Host Process"):
        start_issue_work(
            project, "build-observer", lookup=server.lookup, environ=server.claim()
        )


def test_two_root_sessions_of_one_server_hold_their_own_issue_work(
    project: Path, server: Server
) -> None:
    server.turn(project)
    server.turn(project, FORK)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )
    start_issue_work(
        project, "fix-crash", lookup=server.lookup, environ=server.claim(FORK)
    )

    held = {run.session_key: run.issue_id for run in WorkStore(project).active()[0]}
    assert sorted(held.values()) == ["I_crash", "I_observer"]

    stop_issue_work(project, lookup=server.lookup, environ=server.claim(FORK))
    (kept,) = WorkStore(project).active()[0]
    assert kept.issue_id == "I_observer"


def test_a_claim_used_from_another_worktree_is_refused(
    tmp_path: Path, project: Path, server: Server
) -> None:
    server.turn(project)
    linked = linked_worktree(project, tmp_path / "linked", "linked")

    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(
            linked, "build-observer", lookup=server.lookup, environ=server.claim()
        )

    assert f"is at {project} according to its freshest OpenCode hook record" in str(
        refused.value
    )
    assert WorkStore(linked).active()[0] == []


def test_issue_work_survives_a_reload(project: Path, server: Server) -> None:
    server.turn(project)
    start_issue_work(
        project, "build-observer", lookup=server.lookup, environ=server.claim()
    )
    # A reload cleans every instance up before setting any up.
    server.unobserved(project)
    server.register(project)

    resumed = server.event("execution.started", project)

    assert resumed.written == ("UserPromptSubmit",)
    (held,) = [run for run in runs(project, server.lookup) if run.issue_id]
    assert (held.state, held.orphaned) == ("running", False)


# --- The Host Process mode ``integrate --status`` reports --------------------

# A ``--standalone`` client's private server, as the #163 acceptance run
# recorded it at 2.0.22: the client's child, never registered as the service.
STANDALONE = ProcessIdentity(
    4200,
    4150,
    "opencode",
    "Thu Oct 01 09:30:00 2026",
    "/home/person/.opencode/bin/opencode serve --stdio --port 0",
)


def claimed_here(
    tmp_path: Path, project: Path, lookup: ProcessLookup, environ: Mapping[str, str]
) -> list[str]:
    """The lines of ``integrate opencode --status`` about this command's session."""
    messages = integration_status(
        "opencode",
        tmp_path / "opencode-home",
        state_dir=tmp_path / "state",
        current=project,
        lookup=lookup,
        environ={**environ, "XDG_STATE_HOME": str(tmp_path / "xdg-state")},
        version_probe=lambda: "opencode v2.0.22",
    )
    return [
        message
        for message in messages
        if message.startswith(
            ("Agent Session identity claimed here", "OpenCode Host Process mode")
        )
    ]


def test_status_names_the_shared_service_as_a_confirmed_sessions_host(
    tmp_path: Path, project: Path, server: Server
) -> None:
    server.turn(project)

    assert claimed_here(tmp_path, project, server.lookup, server.claim()) == [
        f"Agent Session identity claimed here: OpenCode session {ROOT} (from "
        "OpenCode environment), confirmed by its live hook record",
        f"OpenCode Host Process mode: shared-service (pid {SERVER.pid}, the "
        "shared 'opencode serve --service')",
    ]


def test_status_names_a_standalone_clients_private_server(
    tmp_path: Path, project: Path, below: Callable[..., ProcessLookup]
) -> None:
    standalone = Server(below(STANDALONE), host=STANDALONE)
    standalone.turn(project)

    lines = claimed_here(tmp_path, project, standalone.lookup, standalone.claim())

    assert lines[0].endswith("confirmed by its live hook record")
    assert lines[1:] == [
        f"OpenCode Host Process mode: standalone (pid {STANDALONE.pid}, a "
        "--standalone client's private 'opencode serve --stdio'); this session "
        "moves itself and leads Workers only on the shared service"
    ]


@pytest.mark.parametrize(
    ("lookup", "detail"),
    [
        (unobservable("ps-timeout"), "could not be observed (ps-timeout)"),
        # Observed without its arguments, the server is no mode Dashpot knows.
        (
            table_lookup(
                {
                    SERVER.pid: ProcessIdentity(
                        SERVER.pid, 1, "opencode", SERVER.started_at
                    )
                }
            ),
            "is neither 'opencode serve --service' nor 'opencode serve --stdio'",
        ),
    ],
)
def test_status_reads_a_server_it_cannot_read_as_unknown(
    tmp_path: Path,
    project: Path,
    server: Server,
    lookup: ProcessLookup,
    detail: str,
) -> None:
    server.turn(project)

    lines = claimed_here(tmp_path, project, lookup, server.claim())

    # An unobservable server still reads as unknown, never gone, so the claim
    # stays confirmed and only the mode is in doubt.
    assert lines[0].endswith("hook record")
    assert "confirmed" in lines[0]
    assert lines[1:] == [
        f"OpenCode Host Process mode: unknown (pid {SERVER.pid} {detail}); this "
        "session moves itself and leads Workers only on the shared service"
    ]


def test_status_reads_a_server_that_exits_after_confirming_as_unknown(
    tmp_path: Path,
    project: Path,
    server: Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server.turn(project)
    confirmed = False
    validate = integrate.validate_session_claim

    def confirm(*args: Any, **kwargs: Any) -> Any:
        nonlocal confirmed
        validated = validate(*args, **kwargs)
        confirmed = True
        return validated

    def lookup(pid: int) -> ProcessObservation:
        return ProcessAbsent(pid) if confirmed else server.lookup(pid)

    monkeypatch.setattr(integrate, "validate_session_claim", confirm)

    lines = claimed_here(tmp_path, project, lookup, server.claim())

    assert lines[1:] == [
        f"OpenCode Host Process mode: unknown (pid {SERVER.pid} has exited); this "
        "session moves itself and leads Workers only on the shared service"
    ]


def test_status_names_no_mode_for_a_claim_it_does_not_confirm(
    tmp_path: Path, project: Path, server: Server
) -> None:
    server.turn(project)
    server.event("deleted", project)

    lines = claimed_here(tmp_path, project, server.lookup, server.claim())

    assert len(lines) == 1
    assert "rejected" in lines[0]


# --- The helper -------------------------------------------------------------


def run_helper(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    destination: EventLogDestination,
    request: str,
) -> tuple[int, str, str]:
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    monkeypatch.setattr("sys.stdin", io.StringIO(request))
    code = hook.opencode_main(event_log=destination)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_helper_prints_one_acknowledgment_and_logs_its_outcome(
    project: Path,
    below: Callable[..., ProcessLookup],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        hook,
        "publish_opencode",
        functools.partial(publish_opencode, lookup=below(SERVER)),
    )
    destination = EventLogDestination(tmp_path / "events")
    base = {
        "protocol": 2,
        "generation": GENERATION,
        "pid": SERVER.pid,
        "deadlineMs": 3000,
    }
    session = {"id": ROOT, "root": ROOT, "location": str(project)}

    code, out, _err = run_helper(
        monkeypatch,
        capsys,
        destination,
        json.dumps({**base, "kind": "register", "location": str(project)}),
    )
    for sequence, kind in enumerate(["started", "interrupted"]):
        event = {
            "id": f"evt_{sequence}",
            "type": f"session.execution.{kind}",
            "sequence": sequence,
        }
        if kind == "interrupted":
            event["reason"] = "user"
        run_helper(
            monkeypatch,
            capsys,
            destination,
            json.dumps({**base, "kind": "event", "session": session, "event": event}),
        )

    assert (code, json.loads(out)) == (0, {"result": "accepted", "sessions": []})
    outcomes = [
        event
        for event in written(destination.directory)
        if event["event.name"] == "hook.outcome"
    ]
    assert [
        (
            event["dashpot.process.kind"],
            event["dashpot.hook.event"],
            event.get("dashpot.agent_session.state"),
            event.get("dashpot.hook.reason"),
        )
        for event in outcomes
    ] == [
        ("hook:opencode:register", "register", None, None),
        ("hook:opencode:event", "UserPromptSubmit", "running", None),
        ("hook:opencode:event", "Stop", "waiting", "user"),
    ]


def test_the_helper_answers_a_malformed_request_with_no_acknowledgment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    destination = EventLogDestination(tmp_path / "events")

    code, out, err = run_helper(monkeypatch, capsys, destination, "{not json")

    assert (code, out) == (hook.NON_BLOCKING_FAILURE_EXIT_CODE, "")
    assert "dashpot OpenCode hook" in err
    (outcome,) = [
        event
        for event in written(destination.directory)
        if event["event.name"] == "hook.outcome"
    ]
    assert outcome["dashpot.process.kind"] == "hook:opencode"
    assert outcome["dashpot.outcome.result"] == "failed"
    assert "dashpot.hook.event" not in outcome


def test_the_helper_gives_up_at_its_deadline(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def stalled(*_args: object, **_kwargs: object) -> OpenCodeOutcome:
        time.sleep(5)
        raise AssertionError("the deadline should have interrupted the helper")

    monkeypatch.setattr(hook, "publish_opencode", stalled)
    monkeypatch.setattr(hook, "OPENCODE_DEADLINE_GRACE_SECONDS", 0.05)
    request = {
        "protocol": 2,
        "kind": "register",
        "generation": GENERATION,
        "location": str(project),
        "pid": SERVER.pid,
        "deadlineMs": 50,
    }

    code, out, err = run_helper(
        monkeypatch,
        capsys,
        EventLogDestination(tmp_path / "events"),
        json.dumps(request),
    )

    assert (code, out) == (hook.NON_BLOCKING_FAILURE_EXIT_CODE, "")
    assert "deadline passed" in err
