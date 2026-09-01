from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pydantic
import pytest
from rich.text import Text

import factories
from dashpot.agents import observe_agent_runs
from dashpot.hook_records import write_hook_record
from dashpot.issue_list import row_key
from dashpot.issue_profile import IssueProfile
from dashpot.list_pane import truncate_end, truncate_start
from dashpot.model import (
    AgentRun,
    ObservationTarget,
    ProjectObservation,
    RunState,
)
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.processes import ProcessIdentity
from dashpot.session_list import (
    OUTSIDE_PROJECT_TEXT,
    SESSION_COLUMNS,
    UNBOUND_ISSUE_TEXT,
    SessionListRow,
    build_session_rows,
    query_session_list,
    session_cells,
    session_columns,
)
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
from factories import workspace
from helpers import make_issue, present, required

CURRENT = datetime(2026, 8, 27, 3, 5, tzinfo=UTC)


def issue(issue_id: str, number: int, title: str) -> IssueProfile:
    return make_issue(id=issue_id, number=number, state="open", title=title)


def target(path: str, branch: str | None = "main") -> ObservationTarget:
    return factories.target(path, branch=branch)


def project(
    project_id: str,
    *issues: IssueProfile,
    targets: list[ObservationTarget] | None = None,
) -> ProjectObservation:
    return factories.project(
        project_id, *issues, targets=targets or [target(f"/{project_id}")]
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
    return factories.agent_run(
        run_id,
        project_id,
        harness=harness,
        state=state,
        issue_id=issue_id,
        hint=hint,
        branch=branch,
        target_path=target_path,
        working_directory=working_directory or target_path or f"/{project_id}",
        last_activity_at=last_activity_at,
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
    assert required(by_id[bound.id].issue).title == "Alpha work"
    assert by_id[bound.id].bound_issue_id == "I_alpha#7"
    assert required(by_id[bound.id].project).display_label == "Alpha"
    assert by_id[unbound.id].issue is None
    assert by_id[unbound.id].bound_issue_id is None
    assert required(by_id[elsewhere.id].project).display_label == "Beta"
    assert required(by_id[elsewhere.id].issue).number == 2
    # The rows are a frozen projection: the store's observations stay put.
    with pytest.raises(pydantic.ValidationError):
        result.rows[0].session.state = "running"  # ty: ignore[invalid-assignment]
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

    assert required(rows["work:one"].issue).id == "I_alpha#7"
    assert rows["work:two"].issue is None
    assert rows["work:two"].bound_issue_id == "I_alpha#99"
    cells = session_cells(rows["work:two"], dark=True, now=CURRENT)
    assert cells[4] == "alpha#99"


def test_a_session_without_a_project_observation_still_lists() -> None:
    orphan = session("work:one", "project:missing")

    result = query_session_list(workspace(project("project:alpha"), runs=[orphan]))

    assert result.count == 1
    assert result.rows[0].project is None
    cells = session_cells(result.rows[0], dark=True, now=CURRENT)
    target_cell = cells[2]
    assert isinstance(target_cell, Text)
    assert target_cell.plain == OUTSIDE_PROJECT_TEXT


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
        assert required(row.issue).number == 7
        cells = session_cells(row, dark=True, now=CURRENT, home=root)
        assert cells[3] == "feature"
        assert cells[4] == "#7 Alpha work"
        assert cells[5] == "src"


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
    elsewhere = session("work:two", target_path="/projects/other/worktree")
    result = query_session_list(
        workspace(alpha, runs=[run, elsewhere], issue_runs={"I_alpha#7": ["work:one"]})
    )

    rows = build_session_rows(result, dark=True, now=CURRENT, home=home)
    row = next(item for item in rows if item.key == row_key("session", "work:one"))

    assert row.key == row_key("session", "work:one")
    assert row.issue_id == "I_alpha#7"
    assert len(row.cells) == len(SESSION_COLUMNS)
    state, harness, target_cell, branch, issue_cell, directory, age = row.cells
    assert isinstance(state, Text)
    assert state.plain == "● running"
    assert isinstance(target_cell, str)
    assert isinstance(branch, str)
    assert harness == "Claude Code"
    assert target_cell == truncate_start(
        "~/projects/very/deeply/nested/linked/worktree/checkout", 28
    )
    assert target_cell.startswith("…") and target_cell.endswith("worktree/checkout")
    assert branch == truncate_end("feature/" + "b" * 40, 24)
    assert branch.endswith("…") and len(branch) == 24
    assert issue_cell == truncate_end("#7 " + "A" * 60, 36)
    assert directory == "/elsewhere/on/disk"
    # A running run has no observed turn start here, so its last activity
    # stands in for one; either way the cell says which age it is showing.
    assert age == "running 1h"


def test_unbound_detached_and_quiet_sessions_render_intentional_values() -> None:
    run = session(
        "claude-code-session:two",
        harness="claude-code",
        state="unknown",
        branch=None,
        last_activity_at=None,
    ).model_copy(update={"working_directory": None})
    result = query_session_list(workspace(project("project:alpha"), runs=[run]))

    (row,) = build_session_rows(result, dark=False, now=CURRENT, home=Path("/nowhere"))

    state, _harness, branch, issue_cell, directory, age = row.cells
    assert isinstance(state, Text)
    assert state.plain == "○ unknown"
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


def test_target_collapses_when_every_session_shares_one_worktree() -> None:
    alpha = project("project:alpha")
    here = session("work:one")
    elsewhere = session("work:two", target_path="/project:alpha/wt/issue-42")
    outside = session("work:three", "project:missing")

    one_worktree = query_session_list(workspace(alpha, runs=[here]))
    assert [column.key for column in session_columns(one_worktree)] == [
        "state",
        "harness",
        "branch",
        "issue",
        "directory",
        "activity",
    ]
    (row,) = build_session_rows(one_worktree, dark=True, now=CURRENT)
    assert len(row.cells) == len(SESSION_COLUMNS) - 1

    # Nothing else names the Worktree now, so DIRECTORY carries the whole
    # path rather than the bare "." it would be relative to its target.
    at_root = session("work:root", target_path="/home/ned/projects/alpha")
    deeper = session(
        "work:deep",
        target_path="/home/ned/projects/alpha",
        working_directory="/home/ned/projects/alpha/src/dashpot",
    )
    collapsed = query_session_list(workspace(alpha, runs=[at_root, deeper]))
    directories = {
        str(row.cells[4])
        for row in build_session_rows(
            collapsed, dark=True, now=CURRENT, home=Path("/home/ned")
        )
    }
    assert directories == {"~/projects/alpha", "~/projects/alpha/src/dashpot"}

    # A linked Worktree, or a session that is not in the Project at all, is
    # what the column exists to tell apart.
    for runs in ([here, elsewhere], [here, outside]):
        result = query_session_list(workspace(alpha, runs=list(runs)))
        assert session_columns(result) == SESSION_COLUMNS
        assert all(
            len(row.cells) == len(SESSION_COLUMNS)
            for row in build_session_rows(result, dark=True, now=CURRENT)
        )

    # An empty pane keeps its full header rather than guessing.
    assert session_columns(query_session_list(workspace(alpha))) == SESSION_COLUMNS


def test_activity_says_which_age_it_is_showing() -> None:
    started = "2026-08-27T00:00:00Z"
    turn = "2026-08-27T02:30:00Z"
    activity = "2026-08-27T03:00:00Z"

    def cell(run: AgentRun) -> str:
        result = query_session_list(workspace(project("project:alpha"), runs=[run]))
        (row,) = build_session_rows(result, dark=True, now=CURRENT)
        return str(row.cells[5])

    running = session(
        "work:running", state="running", last_activity_at=activity
    ).model_copy(update={"turn_started_at": turn})
    assert cell(running) == "running 35m"

    waiting = session("work:waiting", state="waiting", last_activity_at=activity)
    assert cell(waiting) == "idle 5m"

    # A turn that started moments ago is a duration, never a point in time.
    fresh = session(
        "work:fresh", state="running", last_activity_at=CURRENT.isoformat()
    ).model_copy(update={"turn_started_at": "2026-08-27T03:04:30Z"})
    assert cell(fresh) == "running <1m"

    # Nothing has observed this run; when its work began is a different fact
    # and is labelled as one.
    unobserved = session(
        "work:unobserved", state="unknown", last_activity_at=None
    ).model_copy(update={"started_at": started})
    assert cell(unobserved) == "started 3h ago"

    blind = session("work:blind", state="unknown", last_activity_at=None)
    assert cell(blind) == "-"


def test_sandboxed_bindings_of_both_harnesses_reach_the_sessions_and_issues_read_models() -> (
    None
):
    """A Work Store record joined by Agent Session Identity binds the Issue."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        hooks = root / "hooks"
        hooks.mkdir()
        worktree = root / "repo"
        worktree.mkdir()
        codex = ProcessIdentity(42, 1, "codex", "Tue Aug 25 01:00:00 2026")
        claude = ProcessIdentity(43, 1, "claude", "Tue Aug 25 01:30:00 2026")
        for harness, session_id, process, state in (
            ("codex", "codex-thread", codex, "running"),
            ("claude-code", "claude-session", claude, "waiting"),
        ):
            # Opt-in from an isolated sandbox records the identity the hook
            # published, without a process of its own to observe.
            WorkStore(worktree).start(
                ActiveWork(
                    session_key=f"{harness}-session-{session_id}",
                    harness=harness,
                    session_label=f"{harness} session {session_id}",
                    session_process=None,
                    issue_id="I_alpha#7",
                    issue_reference="alpha#7",
                    binding_provenance="explicit-reference",
                    started_at="2026-08-24T14:00:00Z",
                    working_directory=str(worktree),
                    branch="feature",
                    session_id=session_id,
                )
            )
            write_hook_record(
                {
                    "version": 2,
                    "sessionId": session_id,
                    "harness": harness,
                    "state": state,
                    "cwd": str(worktree),
                    "repositoryRoot": str(worktree),
                    "branch": "feature",
                    "event": "UserPromptSubmit" if state == "running" else "Stop",
                    "lastActivityAt": "2026-08-27T03:00:00Z",
                    "sessionProcess": process.as_record(),
                },
                hooks,
            )
        targets = {"project:alpha": [target(str(worktree), "feature")]}
        runs, diagnostics = observe_agent_runs(
            targets,
            hooks,
            lookup=lambda pid: present(codex if pid == 42 else claude)(pid),
        )
        alpha = project(
            "project:alpha",
            issue("I_alpha#7", 7, "Alpha work"),
            targets=targets["project:alpha"],
        )
        store = WorkspaceObservationStore(workspace(alpha))
        store.replace_agent_runs(
            runs, {"I_alpha#7": [run.id for run in runs]}, diagnostics
        )

        sessions = store.query_sessions()
        issues = store.query_issues()

        assert diagnostics == []
        assert sessions.count == 2
        by_harness = {row.session.harness: row for row in sessions.rows}
        assert by_harness["codex"].session.state == "running"
        assert by_harness["claude-code"].session.state == "waiting"
        for row in sessions.rows:
            assert required(row.issue).number == 7
            assert session_cells(row, dark=True, now=CURRENT, home=root)[4] == (
                "#7 Alpha work"
            )
        assert len(issues.rows) == 1
        assert sorted(issues.rows[0].session_states) == ["running", "waiting"]
