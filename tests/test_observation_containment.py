"""Agent Run observation contains malformed records and unobservable processes (#542).

A hook or Work Store record is untrusted input: one naming a PID no process
can have, a path holding a NUL, or a harness that is not a name becomes a
Diagnostic, never an exception that loses every other run. A recorded Host
Process is judged by the PID namespace it was recorded in, not by whether
the observer runs in a container. Every read-decide-write of a session's
hook record holds both of its identity's locks, and a conditional change
never creates a store directory. Each test drives a public seam: the
observer with a fake process lookup, the publisher, the ``work`` commands
through the Work Store, the Cleanup preview, and the stores.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dashpot.core.model import AgentRun, Diagnostic
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.sessions import processes
from dashpot.sessions.agents import locate_observation_target, observe_agent_runs
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecord,
    HookRecordStore,
    project_session_store,
    session_directory,
    state_directory,
)
from dashpot.sessions.hook_scan import classify_hook_record
from dashpot.sessions.liveness import LivenessProbe
from dashpot.sessions.processes import (
    AgentAncestry,
    ProcessAbsent,
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
    ProcessUnobservable,
    local_process_lookup,
    observe_agent_ancestry,
)
from dashpot.sessions.session_identity import IssueWorkError
from dashpot.sessions.session_matching import session_storage_key
from dashpot.sessions.work import show_issue_work, start_issue_work, stop_issue_work
from dashpot.sessions.work_reconciliation import locked_session_stores
from dashpot.sessions.work_store import WorkStore
from factories import CLAUDE, CODEX, hook_record, hook_record_document
from helpers import absent, present, table_lookup
from test_deferred_session_end import DAEMON, Settlers, bind, session_end, settle
from test_retained_subagents import publish
from test_work import CODEX_ENVIRON, CODEX_SESSION, repository, target
from test_worker_assignments import WORKER as LISTED_WORKER
from test_worker_assignments import arc, assign

# PID namespaces as ``/proc/self/ns/pid`` names them: the observer's own,
# and a container's the observer cannot see into.
OWN = "pid:[4026531836]"
FOREIGN = "pid:[4026532999]"
OTHER_SESSION = "01a05099-1563-79a3-8504-e30d50949cd9"
SUBAGENT = "a1b2c3d4e5f607183"
SIBLING_AGENT = "a1b2c3d4e5f607184"
# A PID beyond ``pid_t``: ``os.kill`` overflows on it rather than failing.
OVERFLOWING_PID = 2**40


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global store in the test's directory and fix the observer's namespace."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))
    monkeypatch.setattr(processes, "pid_namespace", lambda: OWN)


def observe(
    root: Path, lookup: ProcessLookup = processes.host_process_lookup
) -> tuple[list[AgentRun], list[Diagnostic]]:
    """One observation pass over ``root`` and the global store."""
    return observe_agent_runs(
        {"project:test": [target(root)]}, state_directory(), lookup=lookup
    )


def codes(diagnostics: list[Diagnostic]) -> list[str | None]:
    return [diagnostic.code for diagnostic in diagnostics]


def write_raw(document: dict[str, Any], directory: Path | None = None) -> Path:
    """Store a hook record exactly as given, as a damaged or foreign writer might."""
    directory = directory or state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document['sessionId']}.json"
    path.write_text(json.dumps(document))
    return path


def bound(root: Path, namespace: str | None, process: ProcessIdentity = CODEX) -> str:
    """Bind the Codex session at ``root`` from ``process``, observed in ``namespace``.

    A ``None`` namespace is a record written before one was kept, or on a
    host that names none. Returns the run's session key.
    """
    observed = replace(process, pid_namespace=namespace)
    hook_record(root, CODEX_SESSION, "codex", observed)
    start_issue_work(
        root, "build-observer", lookup=present(observed), environ=CODEX_ENVIRON
    )
    ((work,), _diagnostics) = WorkStore(root).active()
    assert work.session_process is not None
    assert work.session_process.pid_namespace == namespace
    return work.session_key


# --- Records are validated at the seam ----------------------------------------


def test_a_record_whose_cwd_holds_a_nul_is_reported_and_the_rest_observed(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    write_raw(
        hook_record_document(root, OTHER_SESSION, "codex", CODEX, cwd=f"{root}\0x")
    )
    write_raw(hook_record_document(root, CODEX_SESSION, "codex", CODEX))

    runs, diagnostics = observe(root, present(CODEX))

    assert [run.session_id for run in runs] == [CODEX_SESSION]
    assert codes(diagnostics) == ["agent-session-record-unreadable"]
    assert "NUL" in diagnostics[0].message


@pytest.mark.parametrize(
    ("damage", "field"),
    [
        pytest.param(
            {"sessionProcess": {**CODEX.as_record(), "pid": OVERFLOWING_PID}},
            "sessionProcess",
            id="session-process-pid",
        ),
        pytest.param(
            {"sessionProcess": {**CODEX.as_record(), "pid": 0}},
            "sessionProcess",
            id="session-process-pid-zero",
        ),
        pytest.param(
            {
                "liveSubagents": [SUBAGENT],
                "subagentProcesses": {
                    SUBAGENT: {**CLAUDE.as_record(), "pid": OVERFLOWING_PID}
                },
            },
            "subagentProcesses",
            id="subagent-process-pid",
        ),
        pytest.param(
            {"repositoryRoot": "/repo\0x"}, "repositoryRoot", id="repository-root"
        ),
        pytest.param(
            {"liveSubagents": [SUBAGENT], "subagentProcesses": [SUBAGENT]},
            "subagentProcesses",
            id="subagent-processes-not-a-mapping",
        ),
    ],
)
def test_a_malformed_process_or_root_degrades_the_record_without_failing(
    tmp_path: Path, damage: dict[str, Any], field: str
) -> None:
    root = repository(tmp_path / "repo")
    write_raw({**hook_record_document(root, CODEX_SESSION, "codex", CODEX), **damage})
    write_raw(hook_record_document(root, OTHER_SESSION, "codex", CODEX))

    runs, diagnostics = observe(root, bounded)

    assert sorted(run.session_id or "" for run in runs) == sorted(
        [CODEX_SESSION, OTHER_SESSION]
    )
    degraded = [
        diagnostic.message
        for diagnostic in diagnostics
        if diagnostic.code == "agent-session-record-degraded"
    ]
    assert len(degraded) == 1
    assert field in degraded[0]


def test_an_unreadable_sub_agent_host_leaves_each_other_host_its_own(
    tmp_path: Path,
) -> None:
    # The session ended and its own process is gone; each Sub-agent it left
    # stays while its own Host Process is not known gone (ADR 0107).
    root = repository(tmp_path / "repo")
    sibling = ProcessIdentity(200, 1, "claude", "Tue Aug 25 04:00:00 2026")
    raw = {
        **hook_record_document(root, CODEX_SESSION, "claude-code", CLAUDE),
        "state": "ended",
        "event": "SessionEnd",
        "liveSubagents": [SUBAGENT, SIBLING_AGENT],
        "subagentProcesses": {
            SUBAGENT: {**CLAUDE.as_record(), "pid": OVERFLOWING_PID},
            SIBLING_AGENT: sibling.as_record(),
        },
    }
    living = table_lookup({sibling.pid: sibling})

    assert classify_hook_record(raw, LivenessProbe(living)).live_subagents == (
        SUBAGENT,
        SIBLING_AGENT,
    )
    assert classify_hook_record(raw, LivenessProbe(absent())).live_subagents == (
        SUBAGENT,
    )
    path = write_raw(raw)
    observe(root, living)
    assert path.exists()


def test_a_gone_record_without_a_harness_is_pruned_as_a_codex_one(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    document = hook_record_document(root, CODEX_SESSION, "codex", CODEX)
    del document["harness"]
    path = write_raw(document)

    assert observe(root, absent()) == ([], [])
    assert not path.exists()


def bounded(pid: int) -> ProcessObservation:
    """A lookup finding Codex everywhere, which no PID beyond ``pid_t`` may reach.

    The host's own probe overflows on one; its answer then is the next test's.
    """
    assert 0 < pid < 2**31, pid
    return ProcessPresent(CODEX)


def test_a_recorded_path_that_cannot_be_resolved_places_the_session_nowhere(
    tmp_path: Path,
) -> None:
    # The seam refuses such a record; placement still never raises on one.
    root = repository(tmp_path / "repo")
    classified = classify_hook_record(
        hook_record_document(root, CODEX_SESSION, "codex", CODEX),
        LivenessProbe(present(CODEX)),
    )

    for damaged in (
        replace(
            classified,
            published=classified.published.model_copy(update={"cwd": f"{root}\0x"}),
        ),
        replace(
            classified,
            published=classified.published.model_copy(
                update={"repository_root": f"{root}\0x"}
            ),
        ),
    ):
        assert locate_observation_target(damaged, {"project:test": [target(root)]}) == (
            None,
            None,
        )


def test_an_overflowing_pid_reached_without_a_record_is_unobservable() -> None:
    assert local_process_lookup(OVERFLOWING_PID) == ProcessUnobservable(
        OVERFLOWING_PID, "kill-failed"
    )


def test_a_publisher_beside_a_record_naming_an_impossible_host_never_probes_it(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo").resolve()
    document = hook_record_document(root, CODEX_SESSION, "claude-code", CLAUDE)
    write_raw(
        {
            **document,
            "liveSubagents": [SUBAGENT],
            "subagentProcesses": {
                SUBAGENT: {**CLAUDE.as_record(), "pid": OVERFLOWING_PID}
            },
        },
        session_directory(root),
    )

    def claude(pid: int) -> ProcessObservation:
        # The host's probe overflows beyond ``pid_t``; nothing may ask it to.
        assert 0 < pid < 2**31, pid
        return ProcessPresent(CLAUDE) if pid == CLAUDE.pid else ProcessAbsent(pid)

    publication = publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(root),
            "hook_event_name": "UserPromptSubmit",
        },
        process=CLAUDE,
        harness="claude-code",
        lookup=claude,
    )

    assert publication.state == "running"


@pytest.mark.parametrize("harness", [[], {}, 7], ids=["list", "object", "number"])
def test_a_harness_that_is_not_a_name_is_a_diagnostic(
    tmp_path: Path, harness: object
) -> None:
    root = repository(tmp_path / "repo")
    bound(root, None)
    (path,) = WorkStore(root).directory.glob("*.json")
    path.write_text(json.dumps({**json.loads(path.read_text()), "harness": harness}))
    write_raw(
        {
            **hook_record_document(root, OTHER_SESSION, "codex", CODEX),
            "harness": harness,
        }
    )

    active, work_diagnostics = WorkStore(root).active()
    _runs, diagnostics = observe(root, present(CODEX))

    assert active == []
    assert len(work_diagnostics) == 1
    assert "agent-session-record-unreadable" in codes(diagnostics)


def test_a_work_store_record_naming_an_impossible_pid_is_a_diagnostic(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    bound(root, None)
    # A hand edit no writer makes: the Work Store refuses such a PID.
    (path,) = WorkStore(root).directory.glob("*.json")
    record = json.loads(path.read_text())
    record["sessionProcess"]["pid"] = OVERFLOWING_PID
    path.write_text(json.dumps(record))

    active, work_diagnostics = WorkStore(root).active()
    runs, _diagnostics = observe(root)

    assert active == []
    assert len(work_diagnostics) == 1
    assert [run for run in runs if run.issue_id is not None] == []


def test_the_recorded_reason_for_an_unnamed_process_is_the_reported_one(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    write_raw(
        {
            **hook_record_document(root, CODEX_SESSION, "codex", None),
            "sessionProcessUnobservable": "isolated-namespace",
        }
    )

    runs, diagnostics = observe(root, present(CODEX))

    assert [run.session_id for run in runs] == [CODEX_SESSION]
    assert [diagnostic.message for diagnostic in diagnostics] == [
        "Liveness of 1 Agent Session(s) is unknown: isolated-namespace"
    ]


# --- Liveness is judged by the recorded PID namespace -------------------------


@pytest.mark.parametrize(
    ("namespace", "outcome"),
    [
        pytest.param(OWN, "pruned", id="own"),
        pytest.param(FOREIGN, "unknown", id="foreign"),
        pytest.param(None, "pruned", id="legacy"),
    ],
)
def test_a_hook_records_process_is_probed_only_in_its_own_namespace(
    tmp_path: Path, namespace: str | None, outcome: str
) -> None:
    root = repository(tmp_path / "repo")
    path = write_raw(
        hook_record_document(
            root, CODEX_SESSION, "codex", replace(CODEX, pid_namespace=namespace)
        )
    )

    runs, diagnostics = observe(root, absent())

    if outcome == "pruned":
        # Gone in this namespace, or by the lookup's own answer for a record
        # that names none: stale observation state.
        assert (runs, diagnostics) == ([], [])
        assert not path.exists()
        return
    (run,) = runs
    assert run.session_id == CODEX_SESSION
    assert [diagnostic.message for diagnostic in diagnostics] == [
        "Liveness of 1 Agent Session(s) is unknown: isolated-namespace"
    ]
    assert path.exists()


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the observer as if inside a container's PID namespace."""
    monkeypatch.setattr(processes, "process_namespace_is_isolated", lambda: True)


@pytest.mark.usefixtures("isolated")
def test_inside_a_container_a_process_recorded_there_is_observed(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    observed = local_process_lookup(os.getpid())
    assert isinstance(observed, ProcessPresent)
    this = replace(observed.identity, command="codex")
    assert this.pid_namespace == OWN
    write_raw(hook_record_document(root, CODEX_SESSION, "codex", this))
    write_raw(
        hook_record_document(
            root, OTHER_SESSION, "codex", replace(this, pid_namespace=None)
        )
    )

    # The host's own lookup, which hides a process of unknown namespace.
    runs, diagnostics = observe(root)

    assert {run.session_id: run.state for run in runs} == {
        CODEX_SESSION: "running",
        OTHER_SESSION: "unknown",
    }
    assert [diagnostic.message for diagnostic in diagnostics] == [
        "Liveness of 1 Agent Session(s) is unknown: isolated-namespace"
    ]


@pytest.mark.usefixtures("isolated")
def test_inside_a_container_a_harness_sharing_it_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shell = ProcessIdentity(os.getppid(), CODEX.pid, "bash", CODEX.started_at)
    monkeypatch.setattr(
        processes,
        "local_process_lookup",
        table_lookup({shell.pid: shell, CODEX.pid: CODEX}),
    )

    assert observe_agent_ancestry() == AgentAncestry(("codex", CODEX))


@pytest.mark.parametrize(
    ("isolated", "reason"),
    [pytest.param(True, "isolated-namespace", id="isolated"), (False, None)],
)
def test_an_ancestry_without_a_harness_says_whether_one_may_be_hidden(
    monkeypatch: pytest.MonkeyPatch, isolated: bool, reason: str | None
) -> None:
    monkeypatch.setattr(processes, "process_namespace_is_isolated", lambda: isolated)
    monkeypatch.setattr(processes, "local_process_lookup", table_lookup({}))

    assert observe_agent_ancestry() == AgentAncestry(None, reason)


@pytest.mark.usefixtures("isolated")
@pytest.mark.parametrize(
    ("namespace", "orphaned"),
    [
        pytest.param(OWN, True, id="own"),
        pytest.param(FOREIGN, False, id="foreign"),
        pytest.param(None, False, id="legacy"),
    ],
)
def test_inside_a_container_a_run_is_orphaned_only_by_a_process_of_its_namespace(
    tmp_path: Path, namespace: str | None, orphaned: bool
) -> None:
    root = repository(tmp_path / "repo")
    # The recorded PID names this test's process, started at another time:
    # the recorded process is gone wherever it can be probed.
    bound(root, namespace, replace(CODEX, pid=os.getpid()))

    runs, _diagnostics = observe(root)

    (run,) = [run for run in runs if run.issue_id is not None]
    assert run.orphaned is orphaned


@pytest.mark.parametrize(
    ("namespace", "orphaned"),
    [
        pytest.param(OWN, True, id="own"),
        pytest.param(FOREIGN, False, id="foreign"),
        # A record written before the namespace was kept: the lookup decides.
        pytest.param(None, True, id="legacy"),
    ],
)
def test_a_work_store_run_is_orphaned_by_the_namespace_it_records(
    tmp_path: Path, namespace: str | None, orphaned: bool
) -> None:
    root = repository(tmp_path / "repo")
    bound(root, namespace)

    runs, _diagnostics = observe(root, absent())

    (run,) = [run for run in runs if run.issue_id is not None]
    assert run.orphaned is orphaned


@pytest.mark.parametrize("namespace", [OWN, None], ids=["own", "legacy"])
def test_the_work_store_keeps_the_namespace_only_where_one_was_observed(
    tmp_path: Path, namespace: str | None
) -> None:
    root = repository(tmp_path / "repo")
    bound(root, namespace)

    (path,) = WorkStore(root).directory.glob("*.json")
    recorded = json.loads(path.read_text())["sessionProcess"]
    assert recorded.get("pidNamespace") == namespace
    # Absent rather than null, so the shape an older Dashpot wrote is kept.
    assert ("pidNamespace" in recorded) is (namespace is not None)


@pytest.mark.parametrize(
    ("namespace", "stopped"),
    [
        pytest.param(OWN, True, id="own"),
        pytest.param(FOREIGN, False, id="foreign"),
        pytest.param(None, True, id="legacy"),
    ],
)
def test_stop_by_session_key_refuses_a_run_of_another_namespace(
    tmp_path: Path, namespace: str | None, stopped: bool
) -> None:
    root = repository(tmp_path / "repo")
    session_key = bound(root, namespace)

    if not stopped:
        with pytest.raises(IssueWorkError, match="still running"):
            stop_issue_work(root, session_key=session_key, lookup=absent())
        assert len(WorkStore(root).active()[0]) == 1
        return
    (message,) = stop_issue_work(root, session_key=session_key, lookup=absent())
    assert message.startswith("stopped orphaned work on build-observer")
    assert WorkStore(root).active()[0] == []


@pytest.mark.parametrize(
    ("namespace", "replaced"),
    [pytest.param(OWN, True, id="own"), pytest.param(FOREIGN, False, id="foreign")],
)
def test_start_replaces_a_runtime_gone_only_from_its_own_namespace(
    tmp_path: Path, namespace: str, replaced: bool
) -> None:
    root = repository(tmp_path / "repo")
    # The run was recorded under a process that has since gone from here,
    # and the session continues in another.
    bound(root, namespace, replace(CODEX, pid=999))
    hook_record(root, CODEX_SESSION, "codex", CODEX)

    def lookup(pid: int) -> ProcessObservation:
        return ProcessAbsent(pid) if pid == 999 else ProcessPresent(CODEX)

    if not replaced:
        with pytest.raises(IssueWorkError, match="another live or unobservable"):
            start_issue_work(
                root, "build-observer", lookup=lookup, environ=CODEX_ENVIRON
            )
        return
    start_issue_work(root, "build-observer", lookup=lookup, environ=CODEX_ENVIRON)
    ((work,), _diagnostics) = WorkStore(root).active()
    assert work.session_process is not None
    assert work.session_process.pid == CODEX.pid


@pytest.mark.parametrize(
    ("namespace", "description"),
    [
        pytest.param(OWN, "not listed as working", id="own"),
        pytest.param(
            FOREIGN,
            "listed as working, but its session's liveness is unknown",
            id="foreign",
        ),
    ],
)
def test_show_reports_a_leads_workers_by_the_namespace_it_records(
    tmp_path: Path, namespace: str, description: str
) -> None:
    main, first, _second = arc(tmp_path)
    lead = replace(DAEMON, pid_namespace=namespace)
    bind(main, CODEX_SESSION, lead, "arc")
    publish(main, "SubagentStart", LISTED_WORKER, host=lead)
    assign(main, "first", LISTED_WORKER, first)

    shown = show_issue_work(main, lookup=absent())

    assert shown[-1] == (
        f"  assigned Worker {LISTED_WORKER} to first (I_first) at {first}; "
        + description
    )


@pytest.mark.parametrize(
    ("namespace", "detail"),
    [
        pytest.param(OWN, "Orphaned Agent Run on build-observer", id="own"),
        pytest.param(FOREIGN, "(session unknown)", id="foreign"),
    ],
)
def test_the_cleanup_preview_reads_a_run_by_the_namespace_it_records(
    tmp_path: Path, namespace: str, detail: str
) -> None:
    root = repository(tmp_path / "repo").resolve()
    bound(root, namespace)

    blockers = [
        blocker.detail
        for blocker in assess_worktree_occupancy(root, [root], absent())
        if blocker.kind == "agent-run"
    ]

    (blocker,) = blockers
    assert detail in blocker


@pytest.mark.parametrize(
    ("namespace", "ended"),
    [pytest.param(OWN, True, id="own"), pytest.param(FOREIGN, False, id="foreign")],
)
def test_a_settler_ends_runs_only_for_a_daemon_it_can_see(
    tmp_path: Path, namespace: str, ended: bool
) -> None:
    root = repository(tmp_path / "repo").resolve()
    bind(root, CODEX_SESSION, DAEMON, "build-observer")
    settlers = Settlers()
    session_end(root, CODEX_SESSION, replace(DAEMON, pid_namespace=namespace), settlers)
    (deferred,) = settlers.started
    assert type(deferred).parse(deferred.wire()).host.pid_namespace == namespace

    settled = settle(deferred, present(DAEMON))

    assert bool(settled) is ended
    assert (WorkStore(root).active()[0] == []) is ended


# --- One identity's records change under both of its locks --------------------


@pytest.fixture
def stored(tmp_path: Path) -> tuple[HookRecordStore, dict[str, Any]]:
    """A live record of the Codex session under its plain session id, listing a Sub-agent."""
    store = HookRecordStore(tmp_path / "hooks")
    record = {
        **hook_record_document(tmp_path, CODEX_SESSION, "codex", CODEX),
        "liveSubagents": [SUBAGENT],
    }
    write_raw(record, store.directory)
    return store, record


@pytest.fixture
def scoped_key_held(
    stored: tuple[HookRecordStore, dict[str, Any]],
) -> Iterator[Callable[[], None]]:
    """Hold the identity's harness-scoped lock until the returned call releases it."""
    store, _record = stored
    release = threading.Event()
    held = threading.Event()

    def hold() -> None:
        with store.locked(session_storage_key("codex", CODEX_SESSION)):
            held.set()
            release.wait()

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait()
    yield release.set
    release.set()
    holder.join()


def waits_for(release: Callable[[], None], change: Callable[[], object]) -> object:
    """Run ``change`` beside the held lock: it must wait, then finish once released."""
    results: list[object] = []
    changer = threading.Thread(target=lambda: results.append(change()))
    changer.start()
    changer.join(timeout=0.3)
    assert changer.is_alive(), "the change did not wait for the identity's lock"
    release()
    changer.join()
    (result,) = results
    return result


def test_a_prune_waits_for_the_identitys_other_lock(
    stored: tuple[HookRecordStore, dict[str, Any]],
    scoped_key_held: Callable[[], None],
) -> None:
    store, record = stored

    assert waits_for(scoped_key_held, lambda: store.prune(CODEX_SESSION, record))
    assert not store.record_path(CODEX_SESSION).exists()


def test_a_left_behind_release_waits_for_the_identitys_other_lock(
    stored: tuple[HookRecordStore, dict[str, Any]],
    scoped_key_held: Callable[[], None],
) -> None:
    store, record = stored

    assert waits_for(
        scoped_key_held,
        lambda: store.release_left_behind(
            CODEX_SESSION, [SUBAGENT], HookRecord.model_validate(record)
        ),
    )
    kept = json.loads(store.record_path(CODEX_SESSION).read_text())
    assert kept["liveSubagents"] == []


def test_reconciling_hooks_wait_for_the_identitys_other_lock(
    stored: tuple[HookRecordStore, dict[str, Any]],
    scoped_key_held: Callable[[], None],
) -> None:
    store, _record = stored

    def reconcile() -> bool:
        with locked_session_stores(
            [store.directory], [store.directory.parent], CODEX_SESSION, "codex"
        ):
            return True

    assert waits_for(scoped_key_held, reconcile)


def test_a_change_needs_a_key_of_the_records_own_identity(
    stored: tuple[HookRecordStore, dict[str, Any]],
) -> None:
    store, record = stored
    other = {**record, "sessionId": OTHER_SESSION}

    assert not store.prune(CODEX_SESSION, other)
    assert not store.release_left_behind(
        CODEX_SESSION, [SUBAGENT], HookRecord.model_validate(other)
    )
    assert not store.release_left_behind(
        CODEX_SESSION,
        [SUBAGENT],
        HookRecord.model_validate({**record, "harness": "claude-code"}),
    )
    assert store.record_path(CODEX_SESSION).exists()


def test_a_conditional_change_in_a_removed_worktree_creates_nothing(
    tmp_path: Path,
) -> None:
    removed = tmp_path / "removed"
    store = project_session_store(removed)
    record = hook_record_document(removed, CODEX_SESSION, "codex", CODEX)
    ended = {**record, "state": "ended", "liveSubagents": [SUBAGENT]}

    assert not store.prune(CODEX_SESSION, record)
    assert not store.release_left_behind(
        CODEX_SESSION, [SUBAGENT], HookRecord.model_validate(record)
    )
    assert not store.release_subagents(
        CODEX_SESSION,
        [SUBAGENT],
        HookRecord.model_validate(ended),
        session_id=CODEX_SESSION,
    )
    with locked_session_stores(
        [store.directory], [removed], CODEX_SESSION, "codex", create=False
    ):
        pass

    assert not removed.exists()
