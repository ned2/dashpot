"""A Lead's Workers show on the Issues they were assigned to (#243, ADR 0096).

A Lead bound to an Arc Issue declares each Worker it launched with ``work
assign``; observation reports the Worker running while the Lead's hook
records list it, and the Issue list counts it toward the Issue it was
assigned to, never the Lead's. Each test drives the command and observation
seams with hook events published as the harness would.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import factories
from app_harness import (
    PROJECT_ID,
    SequenceCollector,
    SnapshotQuerySource,
    dashboard_app,
    first_load_landed,
    show_query_peer,
    workspace_snapshot,
)
from app_harness import issue as app_issue
from dashpot.core.command_outcomes import OutcomeNote
from dashpot.core.model import AgentRun, AssignedWorker, WorkerState, WorkspaceSnapshot
from dashpot.issues.issue_resolution import IssueResolutionError
from dashpot.observation.issue_list import IssueListRow, row_key
from dashpot.observation.observation_store import WorkspaceObservationStore
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.queries.source_queries import QueryRequest
from dashpot.sessions.agents import observe_agent_runs
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.hook_records import session_directory, state_directory
from dashpot.sessions.processes import ProcessLookup
from dashpot.sessions.session_identity import IssueWorkError
from dashpot.sessions.work import (
    relocate_issue_work,
    show_issue_work,
    start_issue_work,
    stop_issue_work,
)
from dashpot.sessions.work_store import ActiveWork, WorkStore
from dashpot.sessions.worker_assignments import assign_worker, unassign_worker
from dashpot.ui.glyphs import SESSION_STATE_GLYPHS
from dashpot.ui.issue_cells import AgentStateCell
from helpers import (
    absent,
    make_issue,
    present,
    table_lookup,
    unobservable,
    wait_until,
)
from test_deferred_session_end import (
    DAEMON,
    REPLACEMENT,
    Settlers,
    bind,
    session_end,
    settle,
)
from test_retained_subagents import SECOND_WORKER, WORKER, publish, sessions, stored
from test_work import CLAUDE_SESSION, CODEX_SESSION, linked_worktree, target

LEAD = {"CODEX_THREAD_ID": CODEX_SESSION}
CLAUDE_WORKER = "a1b2c3d4e5f607182"
ARC_ISSUES = {
    "arc.md": {"issue_id": "I_arc", "number": 1, "reference": "arc", "title": "Arc"},
    "first.md": {
        "issue_id": "I_first",
        "number": 2,
        "reference": "first",
        "title": "First",
    },
    "second.md": {
        "issue_id": "I_second",
        "number": 3,
        "reference": "second",
        "title": "Second",
    },
}


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def arc(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A Repository whose main checkout holds the Lead and two Issue Worktrees."""
    main = factories.dashpot_project(tmp_path / "repo", issues=ARC_ISSUES).resolve()
    first = linked_worktree(main, tmp_path / "repo-first", "first")
    second = tmp_path / "repo-second"
    factories.git(main, "worktree", "add", "-q", "-b", "second", str(second))
    return main, first, second.resolve()


def leading(main: Path, *workers: str) -> None:
    """Bind the Lead to the Arc at ``main`` and start each Worker."""
    bind(main, CODEX_SESSION, DAEMON, "arc")
    for worker in workers:
        publish(main, "SubagentStart", worker)


def assign(
    main: Path,
    reference: str,
    worker: str,
    worktree: Path,
    *,
    outcome: OutcomeNote | None = None,
) -> list[str]:
    """Assign ``worker`` from the Lead's session, as the Lead's shell would."""
    return assign_worker(
        main,
        reference,
        worker,
        worktree,
        lookup=present(DAEMON),
        environ=LEAD,
        outcome=outcome,
    )


def observed_runs(lookup: ProcessLookup, *worktrees: Path) -> list[AgentRun]:
    """Every observed Agent Run, whatever Diagnostics observation reports."""
    runs, _diagnostics = observe_agent_runs(
        {"project:test": [target(worktree) for worktree in worktrees]},
        state_directory(),
        lookup=lookup,
    )
    return runs


def lead_run(lookup: ProcessLookup, *worktrees: Path) -> AgentRun:
    """The Lead's one observed Agent Run, whatever its process's liveness."""
    (run,) = observed_runs(lookup, *worktrees)
    return run


def states(run: AgentRun) -> dict[str, str | None]:
    """Each assigned Worker's observed state, by Worker."""
    return {worker.worker_id: worker.state for worker in run.workers}


def issue_rows(*runs: AgentRun) -> dict[str, IssueListRow]:
    """The Issue list over the Arc's Issues and ``runs``, by Issue identity."""
    issues = [
        make_issue(
            id=spec["issue_id"],
            number=spec["number"],
            title=spec["title"],
            labels=[],
            assignees=[],
            author=None,
            milestone=None,
            issueType=None,
        )
        for spec in ARC_ISSUES.values()
    ]
    store = WorkspaceObservationStore(
        factories.workspace(factories.project("project:test", *issues))
    )
    bindings: dict[str, list[str]] = {}
    for run in runs:
        if run.issue_id is not None:
            bindings.setdefault(run.issue_id, []).append(run.id)
    store.replace_agent_runs(list(runs), bindings)
    return {row.issue.id: row for row in store.query_issues().rows}


def activity(*runs: AgentRun) -> dict[str, tuple[str, ...]]:
    """Every Issue's activity, by Issue identity."""
    return {issue_id: row.session_states for issue_id, row in issue_rows(*runs).items()}


def test_an_assigned_worker_runs_on_its_own_issue_not_its_leads(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    note = OutcomeNote()
    before = WorkStore(main).active()[0][0]

    messages = assign(main, "first", WORKER, first, outcome=note)

    assert messages == [f"assigned Worker {WORKER} to first (I_first) at {first}"]
    assert note.action == "assigned"
    assert note.issue_id == "I_first"
    assert note.target_path == first
    # The Lead's Agent Run, binding and location are unchanged.
    (after,) = WorkStore(main).active()[0]
    assert (after.run_id, after.issue_id, after.working_directory) == (
        before.run_id,
        before.issue_id,
        before.working_directory,
    )
    assert WorkStore(first).active()[0] == []
    run = lead_run(present(DAEMON), main, first)
    assert run.issue_id == "I_arc"
    assert run.workers == (
        AssignedWorker(
            worker_id=WORKER,
            issue_id="I_first",
            issue_reference_hint="first",
            worktree=str(first),
            assigned_at=after.workers[0].assigned_at,
            state="running",
        ),
    )
    assert activity(run) == {
        "I_arc": ("running",),
        "I_first": ("running",),
        "I_second": (),
    }


def test_ending_one_worker_leaves_the_other_and_the_lead_running(
    tmp_path: Path,
) -> None:
    main, first, second = arc(tmp_path)
    leading(main, WORKER, SECOND_WORKER)
    assign(main, "first", WORKER, first)
    assign(main, "second", SECOND_WORKER, second)
    run = lead_run(present(DAEMON), main)
    assert activity(run) == {
        "I_arc": ("running",),
        "I_first": ("running",),
        "I_second": ("running",),
    }

    publish(main, "SubagentStop", WORKER)

    run = lead_run(present(DAEMON), main)
    assert states(run) == {WORKER: None, SECOND_WORKER: "running"}
    assert run.state == "running"
    assert activity(run) == {
        "I_arc": ("running",),
        "I_first": (),
        "I_second": ("running",),
    }
    # The Lead declared the assignment; the finished Worker keeps it, shown
    # as no longer listed, until the Lead unassigns it or its run ends.
    assert (
        f"  assigned Worker {WORKER} to first (I_first) at {first}; "
        "not listed as working"
    ) in show_issue_work(main, lookup=present(DAEMON))


def test_an_assignment_alone_never_shows_running(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "SubagentStop", WORKER)
    publish(main, "Stop")

    run = lead_run(present(DAEMON), main)

    assert states(run) == {WORKER: None}
    assert activity(run) == {"I_arc": ("waiting",), "I_first": (), "I_second": ()}


def test_an_unassigned_sub_agent_holds_only_its_sessions_issue(
    tmp_path: Path,
) -> None:
    main, _first, _second = arc(tmp_path)
    leading(main, WORKER)
    publish(main, "Stop")

    run = lead_run(present(DAEMON), main)

    assert run.workers == ()
    assert activity(run) == {"I_arc": ("running",), "I_first": (), "I_second": ()}


def test_a_worker_of_an_unobservable_lead_is_unknown(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)

    run = lead_run(unobservable("ps unavailable"), main)

    assert states(run) == {WORKER: "unknown"}
    assert activity(run)["I_first"] == ("unknown",)


def test_a_worker_of_an_orphaned_lead_shows_nothing(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)

    run = lead_run(absent(), main)

    assert run.orphaned
    assert states(run) == {WORKER: None}
    assert activity(run) == {"I_arc": ("orphaned",), "I_first": (), "I_second": ()}


def test_a_worker_its_ended_lead_kept_is_unknown_until_the_run_ends(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "Stop")
    settlers = Settlers()

    assert session_end(main, CODEX_SESSION, DAEMON, settlers).work == "deferred"

    # The end waits on its settler; the run, and so the assignment, stand.
    run = lead_run(present(DAEMON), main)
    assert states(run) == {WORKER: "unknown"}
    assert activity(run)["I_first"] == ("unknown",)


def test_a_worker_is_reassigned_and_unassigned(tmp_path: Path) -> None:
    main, first, second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)

    assert assign(main, "first", WORKER, first) == [
        f"Worker {WORKER} is already assigned to first (I_first) at {first}"
    ]
    note = OutcomeNote()
    assert assign(main, "second", WORKER, second, outcome=note) == [
        f"reassigned Worker {WORKER} from first at {first} "
        f"to second (I_second) at {second}"
    ]
    assert note.action == "reassigned"
    assert activity(lead_run(present(DAEMON), main))["I_second"] == ("running",)

    note = OutcomeNote()
    assert unassign_worker(
        main, WORKER, lookup=present(DAEMON), environ=LEAD, outcome=note
    ) == [f"unassigned Worker {WORKER} from second"]
    assert note.action == "unassigned"
    assert note.issue_id == "I_second"
    run = lead_run(present(DAEMON), main)
    assert run.workers == ()
    assert activity(run)["I_second"] == ()

    note = OutcomeNote()
    assert unassign_worker(
        main, WORKER, lookup=present(DAEMON), environ=LEAD, outcome=note
    ) == [f"this session's Agent Run assigns no Worker {WORKER}"]
    assert note.action == "no-assignment"


@pytest.mark.parametrize(
    ("worker", "worktree", "error"),
    [
        pytest.param(
            "not an id", None, "is not a Sub-agent identity", id="malformed-identity"
        ),
        pytest.param(
            SECOND_WORKER, None, "lists no Sub-agent", id="sub-agent-not-listed"
        ),
        pytest.param(
            WORKER,
            "elsewhere",
            "is not a Worktree of the current Git Repository",
            id="foreign-worktree",
        ),
    ],
)
def test_assignment_refuses_evidence_it_cannot_confirm(
    tmp_path: Path, worker: str, worktree: str | None, error: str
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    target = first if worktree is None else tmp_path / worktree
    target.mkdir(exist_ok=True)

    with pytest.raises(IssueWorkError, match=error):
        assign(main, "first", worker, target)

    assert WorkStore(main).active()[0][0].workers == ()


def test_assignment_refuses_an_unresolved_issue(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)

    with pytest.raises(IssueResolutionError, match="did not match"):
        assign(main, "missing", WORKER, first)

    assert WorkStore(main).active()[0][0].workers == ()


def test_assignment_requires_the_leads_own_issue_work(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    factories.hook_record(main, CODEX_SESSION, "codex", DAEMON)
    publish(main, "SubagentStart", WORKER)

    with pytest.raises(IssueWorkError, match="no active Issue work"):
        assign(main, "first", WORKER, first)
    with pytest.raises(IssueWorkError, match="no active Issue work"):
        unassign_worker(main, WORKER, lookup=present(DAEMON), environ=LEAD)


def test_ending_the_leads_run_ends_its_assignments_and_says_so(
    tmp_path: Path,
) -> None:
    main, first, second = arc(tmp_path)
    leading(main, WORKER, SECOND_WORKER)
    assign(main, "first", WORKER, first)
    assign(main, "second", SECOND_WORKER, second)

    switched = start_issue_work(main, "first", lookup=present(DAEMON), environ=LEAD)

    assert any(
        "ended 2 Worker Assignments of the run on arc "
        f"({WORKER} on first, {SECOND_WORKER} on second)" in message
        for message in switched
    )
    run = lead_run(present(DAEMON), main)
    assert run.issue_id == "I_first"
    assert run.workers == ()

    assign(main, "second", SECOND_WORKER, second)
    stopped = stop_issue_work(main, lookup=present(DAEMON), environ=LEAD)

    assert any(
        f"ended 1 Worker Assignment of the run on first ({SECOND_WORKER} on second)"
        in message
        for message in stopped
    )
    assert sessions(present(DAEMON), main)[0].workers == ()


def test_show_lists_each_assignment_under_its_leads_run(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)

    shown = show_issue_work(main, lookup=present(DAEMON))

    assert shown[-1] == (
        f"  assigned Worker {WORKER} to first (I_first) at {first}; listed as working"
    )


def worker(issue_id: str, state: WorkerState | None = "running") -> AssignedWorker:
    """A Worker assigned to ``issue_id`` at a fixed Worktree, observed in ``state``."""
    return AssignedWorker(
        worker_id=WORKER,
        issue_id=issue_id,
        issue_reference_hint=issue_id.removeprefix("I_"),
        worktree="/repo-worker",
        assigned_at=factories.NOW,
        state=state,
    )


def leading_run(
    *workers: AssignedWorker,
    project_id: str = "project:test",
    arc_id: str = "I_arc",
) -> AgentRun:
    """The Lead's Agent Run on the Arc, carrying ``workers``."""
    return factories.agent_run(
        "codex:lead", project_id, state="waiting", issue_id=arc_id
    ).model_copy(update={"workers": workers})


def test_a_changed_worker_reports_the_issues_it_left_and_joined() -> None:
    store = WorkspaceObservationStore(
        factories.workspace(
            factories.project(
                "project:test",
                *(
                    make_issue(id=issue_id, number=number)
                    for number, issue_id in enumerate(
                        ("I_arc", "I_first", "I_second"), start=1
                    )
                ),
            )
        )
    )
    bindings = {"I_arc": ["codex:lead"]}
    store.replace_agent_runs([leading_run(worker("I_first"))], bindings)

    stopped = store.replace_agent_runs([leading_run(worker("I_first", None))], bindings)
    moved = store.replace_agent_runs([leading_run(worker("I_second"))], bindings)

    assert stopped.issue_keys == frozenset(
        {("project:test", "I_arc"), ("project:test", "I_first")}
    )
    assert moved.issue_keys == frozenset(
        {
            ("project:test", "I_arc"),
            ("project:test", "I_first"),
            ("project:test", "I_second"),
        }
    )
    row = next(row for row in store.query_issues().rows if row.issue.id == "I_second")
    detail = store.detail_for(row)
    assert detail is not None
    assert detail.session_states == ("running",)


def test_a_paged_row_counts_the_workers_assigned_to_its_issue() -> None:
    arc_issue = app_issue("test-repo#1", "Arc")
    first = app_issue("test-repo#2", "First")
    snapshot = workspace_snapshot(arc_issue, first)
    lead = leading_run(worker(first.id), project_id=PROJECT_ID, arc_id=arc_issue.id)
    store = PagedObservationStore(
        snapshot.model_copy(
            update={"agent_runs": (lead,), "issue_runs": {arc_issue.id: (lead.id,)}}
        )
    )
    store.accept_page(
        "issues",
        SnapshotQuerySource(snapshot).query_page(QueryRequest(kind="issues")).page,
    )

    rows = {row.issue.id: row for row in store.query_issues().rows}

    assert rows[first.id].session_states == ("running",)
    assert rows[first.id].observed_runs == ()
    assert rows[arc_issue.id].session_states == ("waiting",)
    detail = store.detail_for(rows[first.id])
    assert detail is not None
    assert detail.session_states == ("running",)


@pytest.mark.asyncio
async def test_the_issue_list_shows_a_worker_running_until_it_stops() -> None:
    arc_issue = app_issue("test-repo#1", "Arc")
    first = app_issue("test-repo#2", "First")

    def observed(state: WorkerState | None) -> WorkspaceSnapshot:
        """The Lead waiting on its Arc while its Worker is ``state``."""
        lead = leading_run(
            worker(first.id, state), project_id=PROJECT_ID, arc_id=arc_issue.id
        )
        return workspace_snapshot(arc_issue, first, runs=[lead]).model_copy(
            update={"issue_runs": {arc_issue.id: (lead.id,), first.id: ()}}
        )

    app = dashboard_app(SequenceCollector(observed("running"), observed(None)))
    async with app.run_test(size=(150, 55)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await show_query_peer(app, pilot)
        table = app.query_screen.queue_table()

        def glyph(issue_id: str) -> str:
            cell = table.get_cell(row_key("issue", issue_id), "agent_state")
            assert isinstance(cell, AgentStateCell)
            return str(cell)

        await wait_until(lambda: glyph(first.id) != "")
        assert glyph(first.id) == SESSION_STATE_GLYPHS["running"].symbol
        assert glyph(arc_issue.id) == SESSION_STATE_GLYPHS["waiting"].symbol

        app.request_refresh("manual")
        await wait_until(lambda: glyph(first.id) == "")
        assert glyph(arc_issue.id) == SESSION_STATE_GLYPHS["waiting"].symbol


def test_a_resumed_worker_runs_again_under_its_assignment(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "SubagentStop", WORKER)
    assert states(lead_run(present(DAEMON), main)) == {WORKER: None}

    # Claude Code's resume of a stopped agent starts it again under its id.
    publish(main, "SubagentStart", WORKER)

    assert activity(lead_run(present(DAEMON), main))["I_first"] == ("running",)


def test_a_late_start_after_the_leads_run_ended_attributes_nothing(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "SubagentStop", WORKER)
    stop_issue_work(main, lookup=present(DAEMON), environ=LEAD)

    publish(main, "SubagentStart", WORKER)

    assert sessions(present(DAEMON), main)[0].workers == ()


def test_contributors_to_one_issue_aggregate_without_clearing_each_other() -> None:
    direct = factories.agent_run(
        "codex:direct", "project:test", state="waiting", issue_id="I_first"
    )
    second = worker("I_first").model_copy(update={"worker_id": SECOND_WORKER})
    both = leading_run(worker("I_first"), second)
    one_stopped = leading_run(worker("I_first", None), second)
    none_working = leading_run(
        worker("I_first", None), second.model_copy(update={"state": None})
    )

    assert activity(direct, both)["I_first"] == ("waiting", "running", "running")
    assert activity(direct, one_stopped)["I_first"] == ("waiting", "running")
    assert activity(direct, none_working)["I_first"] == ("waiting",)


def test_a_relocated_lead_keeps_its_assignments(tmp_path: Path) -> None:
    main, first, second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    # A Lead drains its Workers before it moves.
    publish(main, "SubagentStop", WORKER)
    relocate_issue_work(main, second, lookup=present(DAEMON), environ=LEAD)
    (before,) = WorkStore(main).active()[0]
    publish(main, "SessionEnd")

    publication = publish(second, "SessionStart", host=REPLACEMENT)

    assert publication.work == "relocated"
    (continued,) = WorkStore(second).active()[0]
    assert continued.run_id == before.run_id
    assert continued.workers == before.workers
    assert [worker.issue_id for worker in continued.workers] == ["I_first"]


def test_assignment_refuses_while_a_work_store_record_is_unreadable(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    damaged = WorkStore(first).directory
    damaged.mkdir(parents=True, exist_ok=True)
    (damaged / "codex-1-deadbeef.json").write_text("{")

    with pytest.raises(IssueWorkError, match="repair the Work Store"):
        assign(main, "first", WORKER, first)

    assert WorkStore(main).active()[0][0].workers == ()


def test_assignment_refuses_a_session_with_runs_at_two_worktrees(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    (run,) = WorkStore(main).active()[0]
    WorkStore(first).start(run)

    with pytest.raises(IssueWorkError, match="more than one Worktree"):
        assign(main, "first", WORKER, first)

    assert WorkStore(main).active()[0][0].workers == ()


def test_assignment_overwrites_nothing_when_the_run_changed_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    write = WorkStore.replace_current

    def racing(store: WorkStore, expected: ActiveWork, new: ActiveWork) -> bool:
        """Let another writer change the run just before this one writes."""
        write(store, expected, replace(expected, branch="elsewhere"))
        return write(store, expected, new)

    monkeypatch.setattr(WorkStore, "replace_current", racing)

    with pytest.raises(IssueWorkError, match="changed while its Workers"):
        assign(main, "first", WORKER, first)

    (run,) = WorkStore(main).active()[0]
    assert (run.branch, run.workers) == ("elsewhere", ())


def test_a_run_recorded_without_a_session_identity_reports_no_worker(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    # A record an older Dashpot wrote names no Agent Session Identity.
    (run,) = WorkStore(main).active()[0]
    path = WorkStore(main).directory / f"{run.session_key}.json"
    document = json.loads(path.read_text())
    document["sessionId"] = None
    path.write_text(json.dumps(document))

    # Such a run no longer joins the named hook session, which lists apart.
    (observed,) = (
        run for run in observed_runs(present(DAEMON), main) if run.issue_id == "I_arc"
    )

    assert states(observed) == {WORKER: None}


def test_show_says_when_a_listed_workers_liveness_is_unknown(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)

    shown = show_issue_work(main, lookup=unobservable("ps unavailable"))

    assert shown[-1] == (
        f"  assigned Worker {WORKER} to first (I_first) at {first}; "
        "listed as working, but its session's liveness is unknown"
    )


def test_another_host_processs_record_reports_no_worker(tmp_path: Path) -> None:
    # A restart's replacement reloads the Lead's thread and lists a Sub-agent
    # under the same identity; it is not the run's session's Sub-agent.
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "SubagentStop", WORKER)
    publish(main, "UserPromptSubmit", host=REPLACEMENT)
    publish(main, "SubagentStart", WORKER, host=REPLACEMENT)
    assert (stored(main) or {}).get("liveSubagents") == [WORKER]
    both = table_lookup({DAEMON.pid: DAEMON, REPLACEMENT.pid: REPLACEMENT})

    (run,) = (run for run in observed_runs(both, main) if run.issue_id == "I_arc")

    assert states(run) == {WORKER: None}
    assert activity(run)["I_first"] == ()
    assert show_issue_work(main, lookup=both)[-1] == (
        f"  assigned Worker {WORKER} to first (I_first) at {first}; "
        "not listed as working"
    )


def test_a_settled_end_of_the_lead_ends_its_assignments(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "Stop")
    settlers = Settlers()
    session_end(main, CODEX_SESSION, DAEMON, settlers)
    (deferred,) = settlers.started

    ((_root, ended),) = settle(deferred, present(DAEMON))

    assert [worker.worker_id for worker in ended.workers] == [WORKER]
    assert WorkStore(main).active() == ([], [])
    # The kept record still lists the Worker, but no assignment names it.
    assert all(run.workers == () for run in observed_runs(present(DAEMON), main))


def test_restarting_the_same_issue_ends_the_assignments_too(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)

    restarted = start_issue_work(main, "arc", lookup=present(DAEMON), environ=LEAD)

    assert restarted == [
        "already working on arc; run restarted",
        f"ended 1 Worker Assignment of the run on arc ({WORKER} on first)",
    ]
    assert lead_run(present(DAEMON), main).workers == ()


def test_a_claude_code_worker_runs_until_unassigned_when_no_stop_arrives(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    factories.hook_record(main, CLAUDE_SESSION, "claude-code", factories.CLAUDE)
    lead = {"CLAUDE_CODE_SESSION_ID": CLAUDE_SESSION, "CLAUDE_PID": "7777"}
    live = present(factories.CLAUDE)
    start_issue_work(main, "arc", lookup=live, environ=lead)
    publish_hook_event(
        {
            "session_id": CLAUDE_SESSION,
            "cwd": str(main),
            "hook_event_name": "SubagentStart",
            "agent_id": CLAUDE_WORKER,
        },
        process=factories.CLAUDE,
        harness="claude-code",
        lookup=live,
    )

    assign_worker(main, "first", CLAUDE_WORKER, first, lookup=live, environ=lead)

    # An interrupted Worker may never be reported stopped; the Lead's
    # unassignment is what takes it off the Issue.
    run = lead_run(live, main)
    assert run.harness == "claude-code"
    assert activity(run)["I_first"] == ("running",)
    unassign_worker(main, CLAUDE_WORKER, lookup=live, environ=lead)
    assert activity(lead_run(live, main))["I_first"] == ()


def test_no_worker_counts_toward_an_issue_two_projects_observe() -> None:
    shared = make_issue(id="I_first", number=2)
    store = WorkspaceObservationStore(
        factories.workspace(
            factories.project("project:test", shared),
            factories.project("project:other", shared),
        )
    )
    store.replace_agent_runs([leading_run(worker("I_first"))], {})

    rows = [row for row in store.query_issues().rows if row.issue.id == "I_first"]

    assert len(rows) == 2
    assert all(row.session_states == () for row in rows)
    details = [store.detail_for(row) for row in rows]
    assert all(detail is not None and detail.session_states == () for detail in details)


def test_assignment_refuses_a_worker_only_a_stale_record_lists(
    tmp_path: Path,
) -> None:
    # The Lead moved to another Worktree's store, carrying its Worker, and
    # the Worker stopped there. Its stop now clears the record left behind
    # too (ADR 0102), so this simulates a record a publisher before ADR 0102
    # left listing the Worker: the Lead's freshest record does not list it.
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    publish(first, "UserPromptSubmit")
    publish(first, "SubagentStop", WORKER)
    left = stored(main)
    assert left is not None
    assert left["liveSubagents"] == []
    path = session_directory(main) / f"{CODEX_SESSION}.json"
    path.write_text(json.dumps({**left, "liveSubagents": [WORKER]}))

    with pytest.raises(IssueWorkError, match="lists no Sub-agent"):
        assign(main, "first", WORKER, first)

    # The move carried the Lead's run with it.
    assert WorkStore(main).active()[0] == []
    assert WorkStore(first).active()[0][0].workers == ()


def test_assignment_refuses_a_worker_that_already_finished(tmp_path: Path) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    publish(main, "SubagentStop", WORKER)

    with pytest.raises(IssueWorkError, match="lists no Sub-agent"):
        assign(main, "first", WORKER, first)

    assert WorkStore(main).active()[0][0].workers == ()


def test_an_orphaned_leads_run_neither_takes_nor_shows_a_worker(
    tmp_path: Path,
) -> None:
    main, first, second = arc(tmp_path)
    leading(main, WORKER, SECOND_WORKER)
    assign(main, "first", WORKER, first)
    # The run is still recorded under a Host Process that is gone, as when
    # the Lead's runtime restarted and no hook event has continued it yet.
    (run,) = WorkStore(main).active()[0]
    path = WorkStore(main).directory / f"{run.session_key}.json"
    document = json.loads(path.read_text())
    document["sessionProcess"] = {
        "pid": REPLACEMENT.pid,
        "startedAt": REPLACEMENT.started_at,
    }
    path.write_text(json.dumps(document))

    # Nothing continues an orphaned Codex run on its own: ``work start`` does.
    with pytest.raises(
        IssueWorkError,
        match=r"earlier Host Process, which is gone; recover it with "
        r"'dashpot work start arc'",
    ):
        assign(main, "second", SECOND_WORKER, second)

    assert [worker.worker_id for worker in WorkStore(main).active()[0][0].workers] == [
        WORKER
    ]
    assert show_issue_work(main, lookup=present(DAEMON))[-1] == (
        f"  assigned Worker {WORKER} to first (I_first) at {first}; "
        "not listed as working"
    )
    (observed,) = (
        run for run in observed_runs(present(DAEMON), main) if run.issue_id == "I_arc"
    )
    assert observed.orphaned
    assert states(observed) == {WORKER: None}


def test_a_worker_kept_by_another_host_processs_end_is_unknown(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    leading(main, WORKER)
    assign(main, "first", WORKER, first)
    publish(main, "SubagentStop", WORKER)
    publish(main, "UserPromptSubmit", host=REPLACEMENT)
    publish(main, "SubagentStart", WORKER, host=REPLACEMENT)
    publish(main, "Stop", host=REPLACEMENT)
    session_end(main, CODEX_SESSION, REPLACEMENT, Settlers())
    both = table_lookup({DAEMON.pid: DAEMON, REPLACEMENT.pid: REPLACEMENT})
    assert (stored(main) or {}).get("state") == "ended"

    (run,) = (run for run in observed_runs(both, main) if run.issue_id == "I_arc")

    assert states(run) == {WORKER: "unknown"}
    assert show_issue_work(main, lookup=both)[-1] == (
        f"  assigned Worker {WORKER} to first (I_first) at {first}; "
        "listed as working, but its session's liveness is unknown"
    )


def test_an_orphaned_claude_code_run_waits_for_its_next_hook_event(
    tmp_path: Path,
) -> None:
    main, first, _second = arc(tmp_path)
    factories.hook_record(main, CLAUDE_SESSION, "claude-code", factories.CLAUDE)
    lead = {"CLAUDE_CODE_SESSION_ID": CLAUDE_SESSION, "CLAUDE_PID": "7777"}
    live = present(factories.CLAUDE)
    start_issue_work(main, "arc", lookup=live, environ=lead)
    # The run is still recorded under a Claude Code process that is gone.
    (run,) = WorkStore(main).active()[0]
    path = WorkStore(main).directory / f"{run.session_key}.json"
    document = json.loads(path.read_text())
    document["sessionProcess"] = {"pid": 8888, "startedAt": "Wed Aug 26 09:00:00 2026"}
    path.write_text(json.dumps(document))

    with pytest.raises(IssueWorkError, match="next hook event has continued the run"):
        assign_worker(main, "first", CLAUDE_WORKER, first, lookup=live, environ=lead)
