from __future__ import annotations

from pathlib import Path

import pydantic
import pytest
from rich.text import Text

import factories
from dashpot.issue_list import row_key
from dashpot.model import (
    ObservationTarget,
    ProjectObservation,
    SourceStatus,
    TargetRole,
)
from dashpot.observation_store import WorkspaceObservationStore
from dashpot.worktree_list import (
    WORKTREE_COLUMNS,
    build_worktree_rows,
    query_worktree_list,
    worktree_cells,
)
from factories import session, workspace
from helpers import required


def target(
    path: str,
    *,
    role: TargetRole = "linked",
    branch: str | None = "main",
    head: str = "abcdef1234567",
    dirty: bool | None = False,
    available: bool = True,
) -> ObservationTarget:
    return factories.target(
        path, role=role, branch=branch, head=head, dirty=dirty, available=available
    )


def project(
    project_id: str,
    *targets: ObservationTarget,
    label: str | None = None,
    anchors: tuple[str, ...] | None = None,
    target_status: SourceStatus = "fresh",
) -> ProjectObservation:
    return factories.project(
        project_id,
        label=label,
        targets=targets,
        anchors=anchors,
        target_status=target_status,
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
    # The rows are a frozen projection of the store's observations.
    with pytest.raises(pydantic.ValidationError):
        result.rows[0].target.dirty = True  # ty: ignore[invalid-assignment]
    assert store.query_worktrees().rows[0].target.dirty is False


def test_main_worktree_is_pinned_before_the_existing_path_order() -> None:
    alpha = project(
        "project:alpha",
        target("/alpha-linked", branch="alpha"),
        target("/zeta-main", role="main"),
        target("/zeta-linked", branch="zeta"),
    )

    result = query_worktree_list(workspace(alpha))

    assert [row.target.path for row in result.rows] == [
        "/zeta-main",
        "/alpha-linked",
        "/zeta-linked",
    ]


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
    sessions_cell = cells[4]
    assert isinstance(sessions_cell, Text)
    assert sessions_cell.plain == "● 2"
    main_cells = worktree_cells(rows["/project:alpha"], dark=True)
    assert isinstance(main_cells[4], Text)
    assert main_cells[4].plain == "○ 1"


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
    assert missing_cells[1] == "linked"
    assert missing_cells[2] == "main"
    assert isinstance(missing_cells[3], Text) and missing_cells[3].plain == "unknown"
    assert isinstance(missing_cells[0], Text)
    assert missing_cells[0].plain == "/project:alpha/missing · unavailable"
    assert missing_cells[0].spans[0].style == "#cf222e"

    # A failed topology refresh retains the last good targets as stale; the
    # Project's other rows are not blanked.
    stale = alpha.model_copy(
        update={
            "status": "stale",
            "snapshot": required(alpha.snapshot).model_copy(
                update={"target_status": "stale"}
            ),
        }
    )
    store.replace_project(stale)

    rows = {row.target.path: row for row in store.query_worktrees().rows}
    assert rows["/project:alpha"].freshness == "stale"
    assert rows["/project:alpha/missing"].freshness == "stale"
    path_cell = worktree_cells(rows["/project:alpha"], dark=True)[0]
    assert isinstance(path_cell, Text)
    assert path_cell.plain == "/project:alpha · stale"
    assert path_cell.spans[0].style == "#d29922"


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
    assert added.project.anchors == ("/project:alpha",)
    assert added.anchored is False

    store.replace_project(
        project("project:alpha", target("/project:alpha", role="main"))
    )
    assert [row.target.path for row in store.query_worktrees().rows] == [
        "/project:alpha"
    ]
    # The Project observation still names only its configured anchor.
    assert required(store.project("project:alpha")).anchors == ("/project:alpha",)


def test_worktree_cells_carry_every_scan_level_fact_without_clipping_paths() -> None:
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
    assert main_row.issue_id is None
    path, kind, branch, tree, sessions = main_row.cells
    assert path == "~/projects/alpha"
    assert kind == "main"
    assert branch == "main"
    assert isinstance(tree, Text) and tree.plain == "dirty"
    assert sessions == "-"

    path, kind, branch, tree, sessions = linked_row.cells
    assert path == "~/projects/very/deeply/nested/linked/worktree/checkout"
    assert kind == "linked"
    assert isinstance(branch, str)
    assert branch.endswith("…") and len(branch) == 24
    assert tree == "clean"
    assert isinstance(sessions, Text) and sessions.plain == "● 1"


def test_detached_targets_say_so() -> None:
    alpha = project("project:alpha", target("/project:alpha", role="main", branch=None))
    (row,) = build_worktree_rows(query_worktree_list(workspace(alpha)), dark=False)
    assert row.cells[2] == "detached @ abcdef1"

    without_head = project(
        "project:alpha",
        target("/project:alpha", role="main", branch=None, head=""),
    )
    (row,) = build_worktree_rows(
        query_worktree_list(workspace(without_head)), dark=False
    )
    assert row.cells[2] == "detached"
