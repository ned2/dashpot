from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from rich.text import Text

from dashpot.issue_list import row_key
from dashpot.model import (
    AgentRun,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    RunState,
    SourceStatus,
    TargetRole,
    WorkspaceSnapshot,
)
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.worktree_list import (
    WORKTREE_COLUMNS,
    build_worktree_rows,
    query_worktree_list,
    worktree_cells,
)
from helpers import required

NOW = "2026-08-27T03:00:00Z"


def target(
    path: str,
    *,
    role: TargetRole = "linked",
    branch: str | None = "main",
    head: str = "abcdef1234567",
    dirty: bool | None = False,
    available: bool = True,
) -> ObservationTarget:
    return ObservationTarget(
        path=path,
        head=head,
        branch=branch,
        detached=branch is None,
        dirty=dirty,
        availability="available" if available else "unavailable",
        elapsed_ms=3,
        diagnostics=[],
        role=role,
    )


def project(
    project_id: str,
    *targets: ObservationTarget,
    label: str | None = None,
    anchors: tuple[str, ...] | None = None,
    target_status: SourceStatus = "fresh",
) -> ProjectObservation:
    display_label = label or project_id.removeprefix("project:").title()
    snapshot = ProjectSnapshot(
        project_id=project_id,
        display_label=display_label,
        repository_id=f"repository:{project_id}",
        collected_at=NOW,
        issue_source_status="fresh",
        issue_source_attempted_at=NOW,
        issue_source_last_good_at=NOW,
        observation_targets=list(targets),
        issues=[],
        diagnostics=[],
        target_status=target_status,
    )
    anchor_paths = list(anchors or (f"/{project_id}",))
    return ProjectObservation(
        project_id=project_id,
        display_label=display_label,
        repository_id=snapshot.repository_id,
        workspaces=["test"],
        anchors=anchor_paths,
        primary_anchor=anchor_paths[0],
        status="fresh",
        elapsed_ms=3,
        snapshot=snapshot,
        diagnostics=[],
    )


def session(
    run_id: str, project_id: str, target_path: str, state: RunState = "waiting"
) -> AgentRun:
    return AgentRun(
        id=run_id,
        harness="codex",
        process_or_session=run_id,
        state=state,
        observation_target=target_path,
        observation_project_id=project_id,
        branch="main",
        issue_id=None,
        issue_reference_hint=None,
    )


def workspace(
    *projects: ProjectObservation, runs: list[AgentRun] | None = None
) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        collected_at=NOW,
        elapsed_ms=9,
        projects=list(projects),
        agent_runs=runs or [],
        issue_runs={},
        diagnostics=[],
    )


def test_store_lists_every_target_across_projects_in_topology_order() -> None:
    alpha = project(
        "project:alpha",
        target("/project:alpha/zeta-linked"),
        target("/project:alpha", role="main"),
        target("/project:alpha/beta-linked", branch=None),
        label="Zulu",
    )
    beta = project(
        "project:beta",
        target("/elsewhere/beta-checkout", role="main"),
        label="Alpha",
        anchors=("/elsewhere/beta-checkout",),
    )
    store = WorkspaceObservationStore(workspace(alpha, beta))

    result = store.query_worktrees()

    assert result.revision == 1
    assert result.count == 4
    assert [(row.project.display_label, row.target.path) for row in result.rows] == [
        ("Alpha", "/elsewhere/beta-checkout"),
        ("Zulu", "/project:alpha"),
        ("Zulu", "/project:alpha/beta-linked"),
        ("Zulu", "/project:alpha/zeta-linked"),
    ]
    assert [row.key for row in result.rows] == [
        row_key("worktree", "project:beta", "/elsewhere/beta-checkout"),
        row_key("worktree", "project:alpha", "/project:alpha"),
        row_key("worktree", "project:alpha", "/project:alpha/beta-linked"),
        row_key("worktree", "project:alpha", "/project:alpha/zeta-linked"),
    ]
    assert [row.anchored for row in result.rows] == [True, True, False, False]
    # A detached record, not the path's name, is why the row is linked.
    assert result.rows[2].target.role == "linked"
    assert result.rows[2].target.detached is True
    # The rows are a detached projection of the store's observations.
    result.rows[0].target.dirty = True
    assert store.query_worktrees().rows[0].target.dirty is False


def test_active_sessions_join_the_target_they_are_located_at() -> None:
    alpha = project(
        "project:alpha",
        target("/project:alpha", role="main"),
        target("/project:alpha/linked"),
    )
    runs = [
        session("one", "project:alpha", "/project:alpha/linked", "waiting"),
        session("two", "project:alpha", "/project:alpha/linked", "running"),
        session("three", "project:alpha", "/project:alpha", "unknown"),
        # Located at a path that is no Observation Target of this Project.
        session("four", "project:alpha", "/project:alpha/gone"),
        session("five", "project:beta", "/project:alpha"),
    ]
    store = WorkspaceObservationStore(workspace(alpha, runs=runs))

    rows = {row.target.path: row for row in store.query_worktrees().rows}

    assert [run.id for run in rows["/project:alpha/linked"].sessions] == ["one", "two"]
    assert [run.id for run in rows["/project:alpha"].sessions] == ["three"]
    cells = worktree_cells(rows["/project:alpha/linked"], dark=True)
    sessions_cell = cells[7]
    assert isinstance(sessions_cell, Text)
    assert sessions_cell.plain == "● 2"
    main_cells = worktree_cells(rows["/project:alpha"], dark=True)
    assert isinstance(main_cells[7], Text)
    assert main_cells[7].plain == "○ 1"


def test_unavailable_and_stale_targets_stay_listed_with_honest_state() -> None:
    alpha = project(
        "project:alpha",
        target("/project:alpha", role="main"),
        target("/project:alpha/missing", dirty=None, available=False, head=""),
    )
    store = WorkspaceObservationStore(workspace(alpha))
    fresh = {row.target.path: row for row in store.query_worktrees().rows}
    assert fresh["/project:alpha/missing"].freshness == "unavailable"
    assert fresh["/project:alpha"].freshness == "available"
    missing_cells = worktree_cells(fresh["/project:alpha/missing"], dark=False)
    assert missing_cells[4] == "-"
    assert isinstance(missing_cells[5], Text) and missing_cells[5].plain == "unknown"
    assert isinstance(missing_cells[6], Text)
    assert missing_cells[6].plain == "unavailable"

    # A failed topology refresh retains the last good targets as stale; the
    # Project's other rows are not blanked.
    stale = replace(alpha, status="stale")
    required(stale.snapshot).target_status = "stale"
    store.replace_project(stale)

    rows = {row.target.path: row for row in store.query_worktrees().rows}
    assert rows["/project:alpha"].freshness == "stale"
    assert rows["/project:alpha/missing"].freshness == "stale"
    state_cell = worktree_cells(rows["/project:alpha"], dark=True)[6]
    assert isinstance(state_cell, Text) and state_cell.plain == "stale"


def test_linked_worktree_addition_and_removal_follow_the_observed_topology() -> None:
    store = WorkspaceObservationStore(
        workspace(project("project:alpha", target("/project:alpha", role="main")))
    )
    assert [row.target.path for row in store.query_worktrees().rows] == [
        "/project:alpha"
    ]

    store.replace_project(
        project(
            "project:alpha",
            target("/project:alpha", role="main"),
            target("/project:alpha/new-linked", branch="feature"),
        )
    )
    assert [row.target.path for row in store.query_worktrees().rows] == [
        "/project:alpha",
        "/project:alpha/new-linked",
    ]
    added = store.query_worktrees().rows[1]
    assert added.project.anchors == ["/project:alpha"]
    assert added.anchored is False

    store.replace_project(
        project("project:alpha", target("/project:alpha", role="main"))
    )
    assert [row.target.path for row in store.query_worktrees().rows] == [
        "/project:alpha"
    ]
    # The Project observation still names only its configured anchor.
    assert required(store.project("project:alpha")).anchors == ["/project:alpha"]


def test_worktree_cells_carry_every_scan_level_fact_and_clip_long_values() -> None:
    home = Path("/home/agent")
    long_path = "/home/agent/projects/very/deeply/nested/linked/worktree/checkout"
    alpha = project(
        "project:alpha",
        target("/home/agent/projects/alpha", role="main", dirty=True),
        target(long_path, branch="feature/" + "b" * 40, head="0123456789abcdef"),
        anchors=("/home/agent/projects/alpha",),
    )
    result = query_worktree_list(
        workspace(alpha, runs=[session("s", "project:alpha", long_path, "running")]),
        revision=4,
    )

    main_row, linked_row = build_worktree_rows(result, dark=True, home=home)

    assert result.revision == 4
    assert len(main_row.cells) == len(WORKTREE_COLUMNS)
    assert main_row.key == row_key(
        "worktree", "project:alpha", "/home/agent/projects/alpha"
    )
    assert main_row.project_id == "project:alpha"
    assert main_row.issue_id is None
    project_label, path, role, branch, head, tree, state, sessions = main_row.cells
    assert project_label == "Alpha"
    assert path == "~/projects/alpha"
    assert role == "main · anchor"
    assert branch == "main"
    assert head == "abcdef1"
    assert isinstance(tree, Text) and tree.plain == "dirty"
    assert state == "available"
    assert sessions == "-"

    _, path, role, branch, head, tree, _state, sessions = linked_row.cells
    assert isinstance(path, str)
    assert path.startswith("…") and path.endswith("worktree/checkout")
    assert len(path) == 28
    assert role == "linked"
    assert isinstance(branch, str)
    assert branch.endswith("…") and len(branch) == 24
    assert head == "0123456"
    assert tree == "clean"
    assert isinstance(sessions, Text) and sessions.plain == "● 1"


def test_detached_targets_say_so() -> None:
    alpha = project("project:alpha", target("/project:alpha", role="main", branch=None))
    (row,) = build_worktree_rows(query_worktree_list(workspace(alpha)), dark=False)
    assert row.cells[3] == "detached"
