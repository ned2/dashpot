"""OpenCode sessions through the shared runtime model (ADRs 0077, 0078 and 0080).

Each scenario follows what the #163 acceptance run measured at OpenCode
1.18.30 (``scripts/experiments/opencode-163``): one ``opencode`` backend runs the
plugin's helper and every shell command as its direct children, a session's
status repeats at every step of a turn, a child session names its
``parentID`` and a fork names none, and a replaced plugin instance registers
before its predecessor retires. The plugin's publications are driven through
``publish_opencode`` with a fake process lookup.
"""

from __future__ import annotations

import functools
import io
import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dashpot import hook
from dashpot.core.event_log import EventLogDestination
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_records import (
    session_directory,
    state_directory,
    write_hook_record,
)
from dashpot.sessions.opencode_publish import (
    OpenCodeOutcome,
    parse_publication,
    publish_opencode,
)
from dashpot.sessions.opencode_publishers import (
    PublisherStore,
    corroboration_refusal,
    new_publisher_record,
    publisher_key,
)
from dashpot.sessions.processes import (
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
)
from dashpot.sessions.work import IssueWorkError, start_issue_work, stop_issue_work
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
BACKEND = ProcessIdentity(
    4100,
    4000,
    "opencode",
    "Thu Oct 01 09:00:00 2026",
    "/home/person/.opencode/bin/opencode serve --hostname 127.0.0.1 --port 0",
)
# The same session's backend after an operator restarted it.
RESTARTED = ProcessIdentity(
    4300, 4000, "opencode", "Thu Oct 01 10:00:00 2026", BACKEND.arguments
)
ROOT = "ses_f05e57dcaffegJ87K4r5rjvjSs"
CHILD = "ses_f05e56ef6ffevvmI30laCCAoGe"
FORK = "ses_f05e56a73ffeklp3IYeT79oPjQ"
FIRST = "d7e54b7b-45ab-41b5-9501-898464014ae4"
SECOND = "cf85c0d2-471d-4f93-8f78-c908d1a0e1c1"


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


@pytest.fixture
def below(monkeypatch: pytest.MonkeyPatch) -> Callable[..., ProcessLookup]:
    """Build a lookup whose ancestry walk meets ``hosts`` above a shell, nearest first.

    The helper and every shell command are direct children of the backend;
    every PID not named is gone.
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


class Plugin:
    """One plugin instance: its generation's publications, sequenced per session."""

    def __init__(
        self,
        directory: Path,
        lookup: ProcessLookup,
        generation: str = FIRST,
        backend: ProcessIdentity = BACKEND,
    ) -> None:
        self.directory = directory
        self.lookup = lookup
        self.generation = generation
        self.backend = backend
        self.sequences: dict[str, int] = {}

    def send(self, kind: str, **fields: Any) -> OpenCodeOutcome:
        wire = {
            "protocol": 1,
            "kind": kind,
            "generation": self.generation,
            "directory": str(self.directory),
            "pid": self.backend.pid,
            "deadlineMs": 3000,
            **fields,
        }
        return publish_opencode(parse_publication(json.dumps(wire)), self.lookup)

    def register(self) -> str:
        return self.send("register").result

    def retire(self) -> str:
        return self.send("retire").result

    def session(
        self,
        kind: str,
        session: str = ROOT,
        *,
        parent: str | None = None,
        root: str | None = None,
        sequence: int | None = None,
        **fields: Any,
    ) -> OpenCodeOutcome:
        if sequence is None:
            sequence = self.sequences.get(session, 0) + 1
        self.sequences[session] = max(sequence, self.sequences.get(session, 0))
        return self.send(
            kind,
            sequence=sequence,
            session={
                "id": session,
                "directory": str(self.directory),
                "parentID": parent,
            },
            root=root or (session if parent is None else parent),
            **fields,
        )

    def status(self, status: str, session: str = ROOT, **options: Any) -> str:
        return self.session("status", session, status=status, **options).result

    def bootstrap(self, session: str = ROOT, **options: Any) -> dict[str, Any]:
        command = options.pop("command", f"call_{session[-4:]}")
        return answer(self.session("bootstrap", session, command=command, **options))

    def claimed(self, session: str = ROOT) -> dict[str, str]:
        """The environment the plugin gives a command after its bootstrap."""
        claim = self.bootstrap(session)["claim"]
        return {
            "DASHPOT_OPENCODE_SESSION_ID": claim["sessionID"],
            "DASHPOT_OPENCODE_GENERATION": claim["generation"],
            "DASHPOT_OPENCODE_PID": str(claim["pid"]),
        }


def answer(outcome: OpenCodeOutcome) -> dict[str, Any]:
    """The acknowledgment as the plugin reads it from the helper's stdout."""
    return json.loads(outcome.acknowledgment.wire())


def record(at: Path, session: str = ROOT) -> dict[str, Any] | None:
    """The session's hook record in the Project-local store, if there is one."""
    path = session_directory(at) / f"{session}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def runs(at: Path, lookup: ProcessLookup) -> list[Any]:
    observed, _diagnostics = observe_agent_runs(
        {"project:test": [target(at)]}, state_directory(), lookup=lookup
    )
    return observed


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return repository(tmp_path / "repo").resolve()


@pytest.fixture
def plugin(project: Path, below: Callable[..., ProcessLookup]) -> Plugin:
    instance = Plugin(project, below(BACKEND))
    assert instance.register() == "accepted"
    return instance


# --- Registration and generations -------------------------------------------


def test_one_generation_owns_a_backend_directory_until_it_retires(
    project: Path, plugin: Plugin
) -> None:
    replacement = Plugin(project, plugin.lookup, SECOND)

    assert plugin.register() == "duplicate"
    # OpenCode starts the replacement instance before the old one retires.
    assert replacement.register() == "conflict"
    assert replacement.status("busy") == "rejected"
    assert plugin.retire() == "accepted"
    assert replacement.register() == "accepted"
    assert plugin.register() == "retired"
    assert plugin.status("idle") == "retired"


def test_a_generation_that_never_registered_is_tombstoned_by_its_retirement(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    early = Plugin(project, below(BACKEND))

    assert early.retire() == "accepted"
    assert early.register() == "retired"
    owner = Plugin(project, early.lookup, SECOND)
    assert owner.register() == "accepted"
    assert owner.status("busy") == "accepted"

    # A stranger's retirement neither clears the owner nor its sessions.
    assert Plugin(project, early.lookup, FIRST.replace("d7", "e8")).retire() == (
        "accepted"
    )
    assert owner.status("idle") == "accepted"
    states = {run.session_id: run.state for run in runs(project, owner.lookup)}
    assert states == {ROOT: "waiting"}


def test_a_helper_that_is_not_the_backends_child_publishes_nothing(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    impostor = Plugin(project, below(BACKEND), backend=RESTARTED)
    blind = Plugin(project, unobservable("ps-timeout"))
    alone = Plugin(project, below(CLAUDE))

    assert answer(impostor.send("register")) == {
        "result": "rejected",
        "reason": "backend-not-corroborated",
    }
    assert answer(blind.send("register"))["reason"] == "ps-timeout"
    assert answer(alone.send("register"))["reason"] == "backend-not-found"


def test_registration_reclaims_records_of_backends_proven_gone(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    gone = Plugin(project, below(BACKEND))
    assert gone.register() == "accepted"
    store = PublisherStore(session_directory(project))
    (stale,) = store.record_keys()

    # The backend exits without disposing its plugin, and a new one starts.
    restarted = Plugin(project, below(RESTARTED), SECOND, backend=RESTARTED)
    assert restarted.register() == "accepted"

    assert stale not in store.record_keys()
    assert len(store.record_keys()) == 1


def test_registration_keeps_records_of_live_or_unreadable_backends(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    store = PublisherStore(session_directory(project))
    assert Plugin(project, below(BACKEND)).register() == "accepted"
    # Both backends live; the second's helper meets its own backend first.
    both = below(RESTARTED, BACKEND)
    unreadable = "0" * 64
    store.record_path(unreadable).write_text("{not json")

    other = Plugin(project, both, SECOND, backend=RESTARTED)
    assert other.register() == "accepted"

    assert len(store.record_keys()) == 3


def test_a_backend_that_cannot_be_observed_keeps_its_record(
    project: Path, below: Callable[..., ProcessLookup]
) -> None:
    first = Plugin(project, below(BACKEND))
    assert first.register() == "accepted"
    restarted = below(RESTARTED)

    def blind_to_the_first(pid: int) -> Any:
        return unobservable("ps-timeout")(pid) if pid == BACKEND.pid else restarted(pid)

    second = Plugin(project, blind_to_the_first, SECOND, backend=RESTARTED)
    assert second.register() == "accepted"

    assert len(PublisherStore(session_directory(project)).record_keys()) == 2


def test_a_publication_outside_its_instance_directory_is_refused(
    project: Path, plugin: Plugin, tmp_path: Path
) -> None:
    elsewhere = plugin.send(
        "status",
        sequence=1,
        status="busy",
        session={"id": ROOT, "directory": str(tmp_path), "parentID": None},
        root=ROOT,
    )

    assert answer(elsewhere) == {
        "result": "rejected",
        "reason": "session-outside-instance",
    }
    assert record(project) is None


@pytest.mark.parametrize(
    "wire",
    [
        pytest.param({"kind": "status", "sequence": 1}, id="no-session"),
        pytest.param(
            {
                "kind": "status",
                "sequence": 1,
                "root": CHILD,
                "session": {"id": ROOT, "directory": "/r", "parentID": None},
            },
            id="root-named-as-another",
        ),
        pytest.param(
            {
                "kind": "deleted",
                "sequence": 1,
                "root": ROOT,
                "status": "idle",
                "session": {"id": ROOT, "directory": "/r", "parentID": None},
            },
            id="status-on-deletion",
        ),
        pytest.param({"kind": "register", "surprise": True}, id="unknown-field"),
        pytest.param({"kind": "register", "generation": "../escape"}, id="generation"),
    ],
)
def test_a_malformed_plugin_request_is_refused(wire: dict[str, Any]) -> None:
    request = {
        "protocol": 1,
        "generation": FIRST,
        "directory": "/r",
        "pid": 1,
        "deadlineMs": 10,
        **wire,
    }

    with pytest.raises(ValueError, match="OpenCode plugin request"):
        parse_publication(json.dumps(request))


# --- A root session's activity ----------------------------------------------


def test_a_root_sessions_status_is_its_turn_state(
    project: Path, plugin: Plugin
) -> None:
    assert plugin.status("busy") == "accepted"
    started = record(project)
    assert started is not None
    assert (started["harness"], started["state"], started["event"]) == (
        "opencode",
        "running",
        "UserPromptSubmit",
    )
    assert started["sessionProcess"]["pid"] == BACKEND.pid
    assert started["lastSessionStartAt"] is not None

    assert plugin.status("retry") == "accepted"
    assert plugin.status("idle") == "accepted"
    waiting = record(project)
    assert waiting is not None
    assert (waiting["state"], waiting["event"]) == ("waiting", "Stop")


def test_a_repeated_or_stale_status_writes_nothing(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    plugin.status("idle")
    settled = record(project)

    assert plugin.status("idle") == "duplicate"
    assert plugin.status("busy", sequence=1) == "stale"
    assert record(project) == settled
    assert plugin.status("busy") == "accepted"


def test_a_root_bootstrap_is_acknowledged_with_the_commands_claim(
    project: Path, plugin: Plugin
) -> None:
    acknowledgment = plugin.bootstrap(command="call_root_1")

    assert acknowledgment == {
        "result": "accepted",
        "command": "call_root_1",
        "claim": {"sessionID": ROOT, "generation": FIRST, "pid": BACKEND.pid},
    }
    running = record(project)
    assert running is not None
    assert (running["state"], running["event"]) == ("running", "PreToolUse")


def test_a_deleted_session_ends_its_record_and_its_run(
    project: Path, plugin: Plugin
) -> None:
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )
    assert WorkStore(project).active()[0] != []

    deleted = plugin.session("deleted")

    assert deleted.result == "accepted"
    assert deleted.publications[-1].work == "ended"
    assert record(project) is None
    assert WorkStore(project).active()[0] == []
    assert plugin.status("busy") == "rejected"
    assert answer(plugin.session("bootstrap", command="late")) == {
        "result": "rejected",
        "reason": "session-deleted",
    }


# --- Delegated work ---------------------------------------------------------


def test_a_child_session_is_a_sub_agent_of_its_root(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    plugin.status("busy", CHILD, parent=ROOT)
    plugin.status("idle")

    working = record(project)
    assert working is not None
    assert record(project, CHILD) is None
    assert working["liveSubagents"] == [CHILD]
    # The root's own turn stopped, but its Sub-agent is still at work.
    assert working["state"] == "running"

    assert plugin.status("idle", CHILD, parent=ROOT) == "accepted"
    settled = record(project)
    assert settled is not None
    assert (settled["liveSubagents"], settled["state"]) == ([], "waiting")


def test_a_child_bootstrap_gets_no_claim(project: Path, plugin: Plugin) -> None:
    plugin.status("busy")

    acknowledgment = plugin.bootstrap(CHILD, parent=ROOT, command="call_child_1")

    assert acknowledgment == {
        "result": "accepted",
        "reason": "delegated-session",
        "command": "call_child_1",
    }
    working = record(project)
    assert working is not None
    assert working["liveSubagents"] == [CHILD]


def test_a_grandchild_is_a_sub_agent_of_the_root(project: Path, plugin: Plugin) -> None:
    plugin.status("busy")

    plugin.status("busy", FORK, parent=CHILD, root=ROOT)
    plugin.session("deleted", FORK, parent=CHILD, root=ROOT)

    settled = record(project)
    assert settled is not None
    assert settled["liveSubagents"] == []


def test_a_childs_first_word_starts_its_roots_record(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy", CHILD, parent=ROOT)

    started = record(project)
    assert started is not None
    assert (started["state"], started["liveSubagents"]) == ("running", [CHILD])


def test_a_fork_is_a_session_of_its_own_and_inherits_no_run(
    project: Path, plugin: Plugin
) -> None:
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )

    plugin.status("busy", FORK)

    forked = record(project, FORK)
    assert forked is not None
    assert forked["liveSubagents"] == []
    (held,) = WorkStore(project).active()[0]
    assert held.session_id == ROOT
    bound = {run.session_id: run.issue_id for run in runs(project, plugin.lookup)}
    assert bound == {ROOT: "I_observer", FORK: None}


# --- Plugin disposal and replacement ----------------------------------------


def test_a_retired_generations_sessions_read_unknown_until_a_successor_publishes(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    plugin.status("busy", FORK)
    plugin.status("busy", CHILD, parent=ROOT)

    plugin.retire()

    states = {run.session_id: run.state for run in runs(project, plugin.lookup)}
    assert states == {ROOT: "unknown", FORK: "unknown"}
    unobserved = record(project)
    assert unobserved is not None
    assert unobserved["sessionProcessUnobservable"] == "opencode-publisher-retired"

    successor = Plugin(project, plugin.lookup, SECOND)
    assert successor.register() == "accepted"
    assert successor.status("idle") == "accepted"
    observed = record(project)
    assert observed is not None
    assert observed["sessionProcess"]["pid"] == BACKEND.pid
    assert observed["sessionProcessUnobservable"] is None
    # A successor's first word starts the record afresh: the Sub-agent its
    # predecessor saw is not one it can vouch for.
    assert (observed["state"], observed["liveSubagents"]) == ("waiting", [])
    states = {run.session_id: run.state for run in runs(project, plugin.lookup)}
    assert states == {ROOT: "waiting", FORK: "unknown"}


def test_a_retired_generations_sessions_read_gone_once_their_backend_exits(
    project: Path, plugin: Plugin
) -> None:
    # OpenCode retires a generation when its TUI quits, as the backend in the
    # same process exits (ADR 0080): the record still names that backend.
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )
    plugin.retire()

    retired = record(project)
    assert retired is not None
    assert retired["sessionProcess"]["pid"] == BACKEND.pid
    assert retired["sessionProcessUnobservable"] == "opencode-publisher-retired"
    (live,) = runs(project, plugin.lookup)
    assert (live.issue_id, live.state, live.orphaned) == (
        "I_observer",
        "unknown",
        False,
    )

    (exited,) = runs(project, table_lookup({}))
    # Only the Work Store's run is left, orphaned under the gone backend; the
    # session itself is gone, not unknown.
    assert (exited.issue_id, exited.orphaned) == ("I_observer", True)


def test_a_retired_generations_session_stays_unknown_while_its_backend_is_unobservable(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    plugin.retire()

    (observed,) = runs(project, unobservable("ps-timeout"))

    assert (observed.session_id, observed.state) == (ROOT, "unknown")


def test_a_successor_ends_a_session_its_predecessor_last_published(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    plugin.retire()
    successor = Plugin(project, plugin.lookup, SECOND)
    successor.register()

    assert successor.session("deleted").result == "accepted"

    assert record(project) is None


def test_retirement_leaves_another_backends_record_alone(
    project: Path, plugin: Plugin, below: Callable[..., ProcessLookup]
) -> None:
    plugin.status("busy")
    other = Plugin(project, below(RESTARTED), SECOND, backend=RESTARTED)
    other.register()
    other.status("busy")

    plugin.retire()

    moved = record(project)
    assert moved is not None
    assert moved["sessionProcess"]["pid"] == RESTARTED.pid


@pytest.mark.parametrize("claude_ended", [False, True])
def test_retirement_finds_its_record_beside_another_harness_of_the_same_id(
    project: Path, plugin: Plugin, claude_ended: bool
) -> None:
    # Claude Code took the session's plain name first, so OpenCode's record
    # is kept under its harness-scoped one, even once Claude Code's is gone.
    claude = hook_record(project, ROOT, "claude-code", CLAUDE)
    plugin.status("busy")
    if claude_ended:
        write_hook_record(
            hook_record_document(project, ROOT, "claude-code", CLAUDE, state="ended"),
            session_directory(project),
        )

    plugin.retire()

    if claude_ended:
        assert not claude.exists()
    else:
        kept = json.loads(claude.read_text())
        assert (kept["harness"], kept["sessionProcess"]["pid"]) == (
            "claude-code",
            CLAUDE.pid,
        )
    (unobserved,) = [
        json.loads(path.read_text())
        for path in session_directory(project).glob("opencode-session-*.json")
    ]
    assert unobserved["sessionProcessUnobservable"] == "opencode-publisher-retired"


def test_retirement_writes_no_record_its_session_no_longer_has(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    # Something other than this generation ended the record, e.g. a prune.
    write_hook_record(
        hook_record_document(
            project,
            ROOT,
            "opencode",
            BACKEND,
            state="ended",
            at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        ),
        session_directory(project),
    )

    assert plugin.retire() == "accepted"

    assert record(project) is None


# --- Issue work ---------------------------------------------------------------


def test_a_corroborated_command_opts_its_session_in(
    project: Path, plugin: Plugin
) -> None:
    messages = start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )

    assert "started work on build-observer" in messages[0]
    (held,) = WorkStore(project).active()[0]
    assert held.issue_id == "I_observer"
    assert held.session_process is not None
    assert held.session_process.pid == BACKEND.pid


def test_a_retired_generations_claim_corroborates_nothing(
    project: Path, plugin: Plugin
) -> None:
    environ = plugin.claimed()
    plugin.retire()
    Plugin(project, plugin.lookup, SECOND).register()

    with pytest.raises(IssueWorkError, match="no plugin instance publishes it now"):
        start_issue_work(
            project, "build-observer", lookup=plugin.lookup, environ=environ
        )

    assert WorkStore(project).active()[0] == []


def test_a_retired_generations_claim_stays_refused_once_a_successor_publishes(
    project: Path, plugin: Plugin
) -> None:
    environ = plugin.claimed()
    plugin.retire()
    successor = Plugin(project, plugin.lookup, SECOND)
    successor.register()
    successor.status("busy")

    with pytest.raises(IssueWorkError, match="has been retired"):
        start_issue_work(
            project, "build-observer", lookup=plugin.lookup, environ=environ
        )


def test_a_claim_from_a_generation_that_does_not_publish_is_refused(
    project: Path, plugin: Plugin
) -> None:
    environ = {**plugin.claimed(), "DASHPOT_OPENCODE_GENERATION": SECOND}

    with pytest.raises(IssueWorkError, match="no longer publishes"):
        start_issue_work(
            project, "build-observer", lookup=plugin.lookup, environ=environ
        )


def test_a_deleted_sessions_claim_is_refused(project: Path, plugin: Plugin) -> None:
    environ = plugin.claimed()
    plugin.status("busy", FORK)
    # Deleting the session leaves no record to validate the claim against.
    plugin.session("deleted")

    with pytest.raises(IssueWorkError, match="no lifecycle hook record"):
        start_issue_work(
            project, "build-observer", lookup=plugin.lookup, environ=environ
        )


def test_ownership_needs_a_record_and_a_session_opencode_kept(
    project: Path,
) -> None:
    hook_store = session_directory(project)
    store = PublisherStore(hook_store)
    key = publisher_key(BACKEND.key, project)

    assert corroboration_refusal(hook_store, BACKEND, project, FIRST, ROOT) == (
        "no publisher generation is registered for its OpenCode backend"
    )
    owned = new_publisher_record(BACKEND, project).model_copy(
        update={"active": FIRST, "deleted": [ROOT]}
    )
    with store.locked(key):
        store.write(key, owned)

    assert corroboration_refusal(hook_store, BACKEND, project, FIRST, ROOT) == (
        "OpenCode has deleted the session"
    )
    assert corroboration_refusal(hook_store, BACKEND, project, FIRST, FORK) is None


def test_an_explicit_override_cannot_name_an_opencode_session(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")

    with pytest.raises(IssueWorkError, match="carries no publisher generation"):
        start_issue_work(
            project,
            "build-observer",
            lookup=plugin.lookup,
            environ={"DASHPOT_AGENT_SESSION": f"opencode:{ROOT}"},
        )


def test_an_uncorroborated_command_is_told_why(project: Path, plugin: Plugin) -> None:
    plugin.status("busy")

    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(
            project,
            "build-observer",
            lookup=plugin.lookup,
            environ={"DASHPOT_OPENCODE_UNCORROBORATED": "delegated-session"},
        )

    message = str(refused.value)
    assert "running Codex, Claude Code, or OpenCode session" in message
    assert "unsupported" not in message
    assert "no corroborated identity: delegated-session" in message


@pytest.mark.parametrize(
    ("missing", "value"),
    [
        ("DASHPOT_OPENCODE_SESSION_ID", ""),
        ("DASHPOT_OPENCODE_GENERATION", ""),
        ("DASHPOT_OPENCODE_PID", "not-a-pid"),
    ],
)
def test_a_partial_claim_is_no_claim(
    project: Path, plugin: Plugin, missing: str, value: str
) -> None:
    environ = {**plugin.claimed(), missing: value}

    with pytest.raises(IssueWorkError, match="no supported agent session"):
        start_issue_work(
            project, "build-observer", lookup=plugin.lookup, environ=environ
        )


def test_an_opencode_backend_alone_never_corroborates_another_harness(
    project: Path, plugin: Plugin
) -> None:
    """A command under OpenCode that inherited a Codex claim is refused.

    The plugin blanks every inherited claim; without the plugin, the nearest
    host is the OpenCode backend, which the Codex claim cannot describe.
    """
    plugin.status("busy")
    hook_record(project, "019dd9a2-codex", "codex", CODEX)

    def lookup(pid: int) -> ProcessObservation:
        return ProcessPresent(CODEX) if pid == CODEX.pid else plugin.lookup(pid)

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
    lookup = below(host, BACKEND)

    start_issue_work(project, "build-observer", lookup=lookup, environ=environ)

    (held,) = WorkStore(project).active()[0]
    assert held.session_key.startswith(harness)
    assert held.session_process is not None
    assert held.session_process.pid == host.pid


def test_a_restarted_backend_continues_a_run_only_by_explicit_start(
    project: Path, plugin: Plugin, below: Callable[..., ProcessLookup]
) -> None:
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )

    # The backend exits, taking its plugin with it; an operator starts another.
    restarted = Plugin(project, below(RESTARTED), SECOND, backend=RESTARTED)
    assert restarted.register() == "accepted"
    resumed = restarted.session("status", status="busy")

    assert all(item.work == "unchanged" for item in resumed.publications)
    (orphaned,) = [run for run in runs(project, restarted.lookup) if run.issue_id]
    assert orphaned.orphaned is True

    start_issue_work(
        project,
        "build-observer",
        lookup=restarted.lookup,
        environ=restarted.claimed(),
    )
    (held,) = WorkStore(project).active()[0]
    assert held.session_process is not None
    assert held.session_process.pid == RESTARTED.pid
    stop_issue_work(project, lookup=restarted.lookup, environ=restarted.claimed())
    assert WorkStore(project).active()[0] == []


def test_two_root_sessions_of_one_backend_hold_their_own_issue_work(
    project: Path, plugin: Plugin
) -> None:
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )
    start_issue_work(
        project, "fix-crash", lookup=plugin.lookup, environ=plugin.claimed(FORK)
    )

    held = {run.session_key: run.issue_id for run in WorkStore(project).active()[0]}
    assert sorted(held.values()) == ["I_crash", "I_observer"]
    assert len(held) == 2

    stop_issue_work(project, lookup=plugin.lookup, environ=plugin.claimed(FORK))
    (kept,) = WorkStore(project).active()[0]
    assert kept.issue_id == "I_observer"


def test_a_claim_used_from_another_worktree_is_refused(
    tmp_path: Path, project: Path, plugin: Plugin
) -> None:
    environ = plugin.claimed()
    linked = linked_worktree(project, tmp_path / "linked", "linked")

    with pytest.raises(IssueWorkError) as refused:
        start_issue_work(
            linked, "build-observer", lookup=plugin.lookup, environ=environ
        )

    assert f"is at {project} according to its freshest OpenCode hook record" in str(
        refused.value
    )
    assert WorkStore(linked).active()[0] == []
    assert WorkStore(project).active()[0] == []


def test_issue_work_survives_its_plugin_being_replaced(
    project: Path, plugin: Plugin
) -> None:
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )
    plugin.retire()
    successor = Plugin(project, plugin.lookup, SECOND)
    assert successor.register() == "accepted"

    resumed = successor.session("status", status="busy")

    assert all(item.work == "unchanged" for item in resumed.publications)
    (held,) = [run for run in runs(project, plugin.lookup) if run.issue_id]
    assert (held.state, held.orphaned) == ("running", False)
    stop_issue_work(project, lookup=plugin.lookup, environ=successor.claimed())
    assert WorkStore(project).active()[0] == []


def test_deleting_a_root_with_a_live_child_ends_its_record_and_its_run(
    project: Path, plugin: Plugin
) -> None:
    plugin.status("busy")
    plugin.status("busy", CHILD, parent=ROOT)
    start_issue_work(
        project, "build-observer", lookup=plugin.lookup, environ=plugin.claimed()
    )

    assert plugin.session("deleted").result == "accepted"

    assert record(project) is None
    assert WorkStore(project).active()[0] == []
    # The child's last word arrives after its root is gone and revives nothing.
    assert plugin.status("idle", CHILD, parent=ROOT) == "rejected"
    assert record(project) is None


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
        functools.partial(publish_opencode, lookup=below(BACKEND)),
    )
    destination = EventLogDestination(tmp_path / "events")
    request = {
        "protocol": 1,
        "kind": "register",
        "generation": FIRST,
        "directory": str(project),
        "pid": BACKEND.pid,
        "deadlineMs": 3000,
    }

    code, out, _err = run_helper(monkeypatch, capsys, destination, json.dumps(request))
    status = {
        **request,
        "kind": "status",
        "status": "busy",
        "sequence": 1,
        "root": ROOT,
        "session": {"id": ROOT, "directory": str(project), "parentID": None},
    }
    run_helper(monkeypatch, capsys, destination, json.dumps(status))

    assert (code, json.loads(out)) == (0, {"result": "accepted"})
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
        )
        for event in outcomes
    ] == [
        ("hook:opencode:register", "register", None),
        ("hook:opencode:status", "status", "running"),
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
        "protocol": 1,
        "kind": "register",
        "generation": FIRST,
        "directory": str(project),
        "pid": BACKEND.pid,
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


def test_a_directory_git_cannot_answer_for_registers_in_the_global_store(
    tmp_path: Path, below: Callable[..., ProcessLookup]
) -> None:
    # OpenCode reloads an instance whose directory was just removed.
    vanished = Plugin(tmp_path / "removed", below(BACKEND))

    assert vanished.register() == "accepted"

    assert PublisherStore(state_directory()).record_keys() != []


def test_a_project_without_configuration_publishes_to_the_global_store(
    tmp_path: Path, below: Callable[..., ProcessLookup]
) -> None:
    unconfigured = (tmp_path / "scratch").resolve()
    unconfigured.mkdir()
    instance = Plugin(unconfigured, below(BACKEND))

    assert instance.register() == "accepted"
    assert instance.status("busy") == "accepted"

    assert (state_directory() / f"{ROOT}.json").is_file()
    assert PublisherStore(state_directory()).record_keys() != []
