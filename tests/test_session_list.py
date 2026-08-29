from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from rich.text import Text

from dashpot.agents import ProcessIdentity, observe_agent_runs, write_hook_record
from dashpot.issue_list import row_key
from dashpot.list_pane import truncate_end, truncate_start
from dashpot.model import (
    AgentRun,
    Issue,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    RunState,
    WorkspaceSnapshot,
)
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.session_list import (
    SESSION_COLUMNS,
    UNBOUND_ISSUE_TEXT,
    SessionListRow,
    build_session_rows,
    query_session_list,
    session_cells,
)
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
from helpers import present, required

NOW = "2026-08-27T03:00:00Z"
CURRENT = datetime(2026, 8, 27, 3, 5, tzinfo=UTC)


def issue(issue_id: str, number: int, title: str) -> Issue:
    return {
        "id": issue_id,
        "number": number,
        "state": "open",
        "title": title,
        "labels": [],
        "assignees": [],
    }


def target(path: str, branch: str | None = "main") -> ObservationTarget:
    return ObservationTarget(
        path=path,
        head="abcdef123456",
        branch=branch,
        detached=branch is None,
        dirty=False,
        availability="available",
        elapsed_ms=3,
        diagnostics=[],
    )


def project(
    project_id: str, *issues: Issue, targets: list[ObservationTarget] | None = None
) -> ProjectObservation:
    label = project_id.removeprefix("project:").title()
    snapshot = ProjectSnapshot(
        project_id=project_id,
        display_label=label,
        repository_id=f"repository:{project_id}",
        collected_at=NOW,
        issue_source_status="fresh",
        issue_source_attempted_at=NOW,
        issue_source_last_good_at=NOW,
        observation_targets=targets or [target(f"/{project_id}")],
        issues=list(issues),
        diagnostics=[],
    )
    return ProjectObservation(
        project_id=project_id,
        display_label=label,
        repository_id=snapshot.repository_id,
        workspaces=["test"],
        anchors=[f"/{project_id}"],
        primary_anchor=f"/{project_id}",
        status="fresh",
        elapsed_ms=3,
        snapshot=snapshot,
        diagnostics=[],
    )


def session(
    run_id: str,
    project_id: str = "project:alpha",
    *,
    harness: str = "codex",
    state: RunState = "waiting",
    issue_id: str | None = None,
    hint: str | None = None,
    branch: str | None = "main",
    target_path: str | None = None,
    working_directory: str | None = None,
    last_activity_at: str | None = "2026-08-27T03:00:00Z",
) -> AgentRun:
    return AgentRun(
        id=run_id,
        harness=harness,
        process_or_session=run_id,
        state=state,
        observation_target=target_path or f"/{project_id}",
        observation_project_id=project_id,
        branch=branch,
        issue_id=issue_id,
        issue_reference_hint=hint,
        working_directory=working_directory or target_path or f"/{project_id}",
        last_activity_at=last_activity_at,
    )


def workspace(
    *projects: ProjectObservation,
    runs: list[AgentRun] | None = None,
    issue_runs: dict[str, list[str]] | None = None,
) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        collected_at=NOW,
        elapsed_ms=9,
        projects=list(projects),
        agent_runs=runs or [],
        issue_runs=issue_runs or {},
        diagnostics=[],
    )


def test_store_lists_every_active_session_once_with_its_relationships() -> None:
    alpha = project("project:alpha", issue("I_alpha#7", 7, "Alpha work"))
    beta = project("project:beta", issue("I_beta#2", 2, "Beta work"))
    bound = session("work:codex:one", issue_id="I_alpha#7", hint="alpha#7")
    unbound = session("claude-code-session:two", harness="claude-code")
    elsewhere = session(
        "work:codex:three", "project:beta", issue_id="I_beta#2", hint="beta#2"
    )
    store = WorkspaceObservationStore(
        workspace(
            alpha,
            beta,
            runs=[bound, unbound, elsewhere],
            issue_runs={"I_alpha#7": [bound.id], "I_beta#2": [elsewhere.id]},
        )
    )

    result = store.query_sessions()

    assert result.revision == store.revision == 1
    assert result.count == 3
    assert [row.key for row in result.rows] == [
        row_key("session", "claude-code-session:two"),
        row_key("session", "work:codex:one"),
        row_key("session", "work:codex:three"),
    ]
    by_id = {row.session.id: row for row in result.rows}
    assert required(by_id[bound.id].issue)["title"] == "Alpha work"
    assert by_id[bound.id].bound_issue_id == "I_alpha#7"
    assert required(by_id[bound.id].project).display_label == "Alpha"
    assert by_id[unbound.id].issue is None
    assert by_id[unbound.id].bound_issue_id is None
    assert required(by_id[elsewhere.id].project).display_label == "Beta"
    assert required(by_id[elsewhere.id].issue)["number"] == 2
    # The rows are a detached projection: the store's observations stay put.
    result.rows[0].session.state = "running"
    assert store.query_sessions().rows[0].session.state == "waiting"


def test_sessions_sort_by_state_then_most_recent_activity_then_identity() -> None:
    runs = [
        session("waiting-old", state="waiting", last_activity_at="2026-08-27T01:00Z"),
        session("unknown", state="unknown", last_activity_at=None),
        session("running-b", state="running", last_activity_at="2026-08-27T02:00Z"),
        session("running-a", state="running", last_activity_at="2026-08-27T02:00Z"),
        session("running-new", state="running", last_activity_at="2026-08-27T02:30Z"),
        session("waiting-quiet", state="waiting", last_activity_at=None),
        session("waiting-new", state="waiting", last_activity_at="2026-08-27T02:59Z"),
    ]

    result = query_session_list(workspace(project("project:alpha"), runs=runs))

    assert [row.session.id for row in result.rows] == [
        "running-new",
        "running-a",
        "running-b",
        "waiting-new",
        "waiting-old",
        "waiting-quiet",
        "unknown",
    ]


def test_accepted_binding_wins_over_the_record_hint_and_unknown_issues_keep_it() -> (
    None
):
    alpha = project("project:alpha", issue("I_alpha#7", 7, "Alpha work"))
    transferred = session("work:one", issue_id="I_alpha#1", hint="alpha#1")
    unlisted = session("work:two", issue_id="I_alpha#99", hint="alpha#99")
    store = WorkspaceObservationStore(
        workspace(
            alpha, runs=[transferred, unlisted], issue_runs={"I_alpha#7": ["work:one"]}
        )
    )

    rows = {row.session.id: row for row in store.query_sessions().rows}

    assert required(rows["work:one"].issue)["id"] == "I_alpha#7"
    assert rows["work:two"].issue is None
    assert rows["work:two"].bound_issue_id == "I_alpha#99"
    cells = session_cells(rows["work:two"], dark=True, now=CURRENT)
    assert cells[5] == "alpha#99"


def test_a_session_without_a_project_observation_still_lists() -> None:
    orphan = session("work:one", "project:missing")

    result = query_session_list(workspace(project("project:alpha"), runs=[orphan]))

    assert result.count == 1
    assert result.rows[0].project is None
    cells = session_cells(result.rows[0], dark=True, now=CURRENT)
    assert cells[2] == "project:missing"


def test_correlated_hook_and_work_records_are_one_session_row() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        hooks = root / "hooks"
        hooks.mkdir()
        worktree = root / "repo"
        (worktree / "src").mkdir(parents=True)
        process = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")
        WorkStore(worktree).start(
            ActiveWork(
                session_key="codex-42-abcd1234",
                harness="codex",
                session_label="codex pid 42",
                session_process=SessionProcess(process.pid, process.started_at),
                issue_id="I_alpha#7",
                issue_reference="alpha#7",
                binding_provenance="explicit-reference",
                started_at="2026-08-24T14:00:00Z",
                working_directory=str(worktree / "src"),
                branch="feature",
            )
        )
        write_hook_record(
            {
                "version": 2,
                "sessionId": "session-a",
                "harness": "codex",
                "state": "running",
                "cwd": str(worktree / "src"),
                "repositoryRoot": str(worktree),
                "branch": "feature",
                "event": "PreToolUse",
                "lastActivityAt": "2026-08-27T03:00:00Z",
                "sessionProcess": process.as_record(),
            },
            hooks,
        )
        targets = {"project:alpha": [target(str(worktree), "feature")]}
        runs, diagnostics = observe_agent_runs(targets, hooks, lookup=present(process))
        alpha = project(
            "project:alpha",
            issue("I_alpha#7", 7, "Alpha work"),
            targets=targets["project:alpha"],
        )
        store = WorkspaceObservationStore(workspace(alpha))
        store.replace_agent_runs(
            runs, {"I_alpha#7": [run.id for run in runs]}, diagnostics
        )

        result = store.query_sessions()

        assert diagnostics == []
        assert result.count == 1
        row = result.rows[0]
        assert row.session.state == "running"
        assert required(row.issue)["number"] == 7
        cells = session_cells(row, dark=True, now=CURRENT, home=root)
        assert cells[4] == "feature"
        assert cells[5] == "#7 Alpha work"
        assert cells[6] == "src"


def test_session_cells_carry_every_scan_level_fact_and_truncate_honestly() -> None:
    home = Path("/home/agent")
    alpha = project("project:alpha", issue("I_alpha#7", 7, "A" * 60))
    long_path = "/home/agent/projects/very/deeply/nested/linked/worktree/checkout"
    run = session(
        "work:one",
        harness="claude-code",
        state="running",
        issue_id="I_alpha#7",
        branch="feature/" + "b" * 40,
        target_path=long_path,
        working_directory="/elsewhere/on/disk",
        last_activity_at="2026-08-27T02:00:00Z",
    )
    result = query_session_list(
        workspace(alpha, runs=[run], issue_runs={"I_alpha#7": ["work:one"]})
    )

    (row,) = build_session_rows(result, dark=True, now=CURRENT, home=home)

    assert row.key == row_key("session", "work:one")
    assert row.project_id == "project:alpha"
    assert row.issue_id == "I_alpha#7"
    assert len(row.cells) == len(SESSION_COLUMNS)
    state, harness, project_label, target_cell, branch, issue_cell, directory, age = (
        row.cells
    )
    assert isinstance(state, Text)
    assert state.plain == "● running"
    assert isinstance(target_cell, str)
    assert isinstance(branch, str)
    assert harness == "Claude Code"
    assert project_label == "Alpha"
    assert target_cell == truncate_start(
        "~/projects/very/deeply/nested/linked/worktree/checkout", 28
    )
    assert target_cell.startswith("…") and target_cell.endswith("worktree/checkout")
    assert branch == truncate_end("feature/" + "b" * 40, 24)
    assert branch.endswith("…") and len(branch) == 24
    assert issue_cell == truncate_end("#7 " + "A" * 60, 36)
    assert directory == "/elsewhere/on/disk"
    assert age == "1h ago"


def test_unbound_detached_and_quiet_sessions_render_intentional_values() -> None:
    run = session(
        "claude-code-session:two",
        harness="claude-code",
        state="unknown",
        branch=None,
        last_activity_at=None,
    )
    run.working_directory = None
    result = query_session_list(workspace(project("project:alpha"), runs=[run]))

    (row,) = build_session_rows(result, dark=False, now=CURRENT, home=Path("/nowhere"))

    state, _harness, _project, target_cell, branch, issue_cell, directory, age = (
        row.cells
    )
    assert isinstance(state, Text)
    assert state.plain == "○ unknown"
    assert target_cell == "/project:alpha"
    assert branch == "detached"
    assert isinstance(issue_cell, Text)
    assert issue_cell.plain == UNBOUND_ISSUE_TEXT
    assert directory == "-"
    assert age == "-"
    assert row.issue_id is None


def test_state_glyphs_are_distinct_and_themed() -> None:
    rows = {
        state: build_session_rows(
            query_session_list(
                workspace(project("project:alpha"), runs=[session("s", state=state)])
            ),
            dark=dark,
            now=CURRENT,
        )[0].cells[0]
        for state in ("running", "waiting", "unknown")
        for dark in (True, False)
    }
    glyphs = {str(cell)[0] for cell in rows.values()}
    assert len(glyphs) == 3
    assert all(isinstance(cell, Text) and cell.style for cell in rows.values())


def test_session_row_is_a_single_projection_of_the_agent_run() -> None:
    row = SessionListRow(row_key("session", "s"), session("s"), None)
    assert row.issue is None
    assert row.bound_issue_id is None
