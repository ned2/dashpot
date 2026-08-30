from __future__ import annotations

from datetime import UTC, datetime

from rich.text import Text

from dashpot.branch_list import (
    BRANCH_COLUMNS,
    branch_cells,
    branch_note,
    build_branch_rows,
    fetch_age_text,
    query_branch_list,
)
from dashpot.issue_list import row_key
from dashpot.model import Branch, ProjectObservation
from dashpot.observation_store import WorkspaceObservationStore
from helpers import snapshot_of
from test_worktree_list import NOW, project, session, target, workspace

CLOCK = datetime(2026, 8, 27, 3, 0, 0, tzinfo=UTC)


def local(
    name: str,
    *,
    head: str = "abcdef1234567",
    upstream: str | None = None,
    ahead: int | None = None,
    behind: int | None = None,
    gone: bool = False,
    committed_at: str = "2026-08-27T02:00:00Z",
    checked_out_at: str | None = None,
    unintegrated_commits: int | None = None,
) -> Branch:
    if upstream is not None and ahead is None and not gone:
        ahead, behind = 0, 0
    return Branch(
        refname=f"refs/heads/{name}",
        name=name,
        remote=None,
        head=head,
        committed_at=committed_at,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        upstream_gone=gone,
        checked_out_at=checked_out_at,
        unintegrated_commits=unintegrated_commits,
    )


def remote(
    name: str,
    *,
    remote: str = "origin",
    head: str = "fedcba7654321",
    committed_at: str = "2026-08-27T02:00:00Z",
) -> Branch:
    return Branch(
        refname=f"refs/remotes/{remote}/{name}",
        name=name,
        remote=remote,
        head=head,
        committed_at=committed_at,
    )


def branchy_project(
    project_id: str,
    *branches: Branch,
    fetched_at: str | None = NOW,
    integration_ref: str | None = "refs/remotes/origin/main",
) -> ProjectObservation:
    observation = project(project_id, target(f"/{project_id}", role="main"))
    snapshot_of(observation).branches = list(branches)
    snapshot_of(observation).fetched_at = fetched_at
    snapshot_of(observation).integration_ref = integration_ref
    return observation


def test_local_and_remote_refs_of_one_name_are_one_row() -> None:
    observation = branchy_project(
        "project:one",
        local("main", upstream="origin/main", checked_out_at="/project:one"),
        remote("main"),
        remote("main", remote="upstream", head="111111"),
        local("feature", upstream="origin/feature", ahead=2, behind=1),
        remote("feature"),
        local("scratch"),
        remote("elsewhere"),
    )

    result = query_branch_list(workspace(observation))

    assert result.count == 4
    assert result.fetched_at == NOW
    assert result.integration_refs == ("refs/remotes/origin/main",)
    by_name = {row.name: row for row in result.rows}
    assert set(by_name) == {"main", "feature", "scratch", "elsewhere"}
    main = by_name["main"]
    assert main.key == row_key("branch", "project:one", "main")
    assert main.local is not None and main.local.upstream == "origin/main"
    assert [ref.remote for ref in main.remotes] == ["origin", "upstream"]
    assert [target.path for target in main.worktrees] == ["/project:one"]
    assert by_name["scratch"].remotes == ()
    assert by_name["elsewhere"].local is None


def test_checked_out_branches_lead_then_the_most_recent_commit() -> None:
    observation = branchy_project(
        "project:one",
        local("old-but-checked-out", committed_at="2026-08-01T00:00:00Z"),
        local("newest", committed_at="2026-08-27T02:59:00Z"),
        local("older", committed_at="2026-08-26T00:00:00Z"),
        remote("zeta", committed_at="2026-08-26T00:00:00Z"),
        remote("alpha", committed_at="2026-08-26T00:00:00Z"),
    )
    snapshot_of(observation).observation_targets = [
        target("/project:one", role="main", branch="old-but-checked-out")
    ]

    result = query_branch_list(workspace(observation))

    assert [row.name for row in result.rows] == [
        "old-but-checked-out",
        "newest",
        "alpha",
        "older",
        "zeta",
    ]


def test_sessions_join_the_branch_they_are_on_and_the_store_serves_the_query() -> None:
    observation = branchy_project(
        "project:one", local("issue/1", upstream="origin/issue/1"), remote("issue/1")
    )
    on_branch = session("codex:1", "project:one", "/project:one", state="running")
    on_branch.branch = "issue/1"
    elsewhere = session("codex:2", "project:one", "/project:one")
    store = WorkspaceObservationStore(
        workspace(observation, runs=[on_branch, elsewhere])
    )

    result = store.query_branches()

    assert result.revision == 1
    assert [row.name for row in result.rows] == ["issue/1"]
    assert [run.id for run in result.rows[0].sessions] == ["codex:1"]


def test_branch_cells_carry_every_scan_level_fact() -> None:
    long_name = "feature/" + "x" * 60
    observation = branchy_project(
        "project:one",
        local(
            "main",
            upstream="origin/main",
            checked_out_at="/home/ned/project:one",
            unintegrated_commits=0,
        ),
        remote("main"),
        local(
            "ahead-behind",
            upstream="origin/ahead-behind",
            ahead=3,
            behind=2,
            unintegrated_commits=3,
        ),
        local("gone", upstream="origin/gone", gone=True),
        local(long_name, unintegrated_commits=0),
        remote("remote-only"),
    )
    snapshot_of(observation).observation_targets = [
        target("/home/ned/project:one", role="main", branch="main")
    ]
    on_main = session("codex:1", "project:one", "/home/ned/project:one")
    on_main.branch = "main"
    result = query_branch_list(workspace(observation, runs=[on_main]))
    by_name = {row.name: row for row in result.rows}

    def plain(cells: tuple[str | Text, ...]) -> list[str]:
        return [str(cell) for cell in cells]

    main = branch_cells(by_name["main"], dark=True, now=CLOCK)
    assert plain(main) == [
        "main",
        "✓",
        "✓",
        "=",
        "⊆",
        "◐ 1",
        "1h ago",
    ]
    drifted = branch_cells(by_name["ahead-behind"], dark=True, now=CLOCK)
    assert isinstance(drifted[3], Text)
    assert drifted[3].plain == "↑3 ↓2"
    assert str(drifted[3].style) == "#d29922"
    assert isinstance(drifted[4], Text)
    assert drifted[4].plain == "↑3"
    assert str(drifted[4].style) == "#d29922"
    gone = branch_cells(by_name["gone"], dark=False, now=CLOCK)
    assert isinstance(gone[3], Text)
    assert (gone[3].plain, str(gone[3].style)) == ("✗", "#cf222e")
    assert isinstance(gone[4], Text)
    assert (gone[4].plain, str(gone[4].style)) == ("⊘", "#cf222e")
    no_upstream = branch_cells(by_name[long_name], dark=True, now=CLOCK)
    assert str(no_upstream[0]) == "feature/" + "x" * 39 + "…"
    assert isinstance(no_upstream[3], Text)
    assert no_upstream[3].plain == "∅"
    assert no_upstream[4] == "⊆"
    assert str(no_upstream[5]) == "-"
    remote_only = branch_cells(by_name["remote-only"], dark=True, now=CLOCK)
    assert plain(remote_only[:5]) == ["remote-only", "", "✓", "-", "-"]
    assert plain(remote_only[5:]) == ["-", "1h ago"]

    rows = build_branch_rows(result, dark=True, now=CLOCK)
    assert [row.key for row in rows] == [row.key for row in result.rows]
    assert len(rows[0].cells) == len(BRANCH_COLUMNS)
    assert [column.label for column in BRANCH_COLUMNS] == [
        "BRANCH",
        "LOCAL",
        "REMOTE",
        "UPSTREAM",
        "INTEGRATED",
        "SESSIONS",
        "LAST COMMIT",
    ]


def test_fetch_age_is_honest() -> None:
    observation = branchy_project("project:one", local("main"), fetched_at=None)
    snapshot_of(observation).target_status = "stale"

    result = query_branch_list(workspace(observation))

    assert result.fetched_at is None
    assert fetch_age_text(None, CLOCK) == "remote never fetched"
    assert fetch_age_text("2026-08-27T00:00:00Z", CLOCK) == "remote last fetched 3h ago"
    assert branch_note((), None, CLOCK) == (
        "integration unavailable · remote never fetched"
    )
    assert (
        branch_note(("refs/remotes/origin/main",), "2026-08-27T00:00:00Z", CLOCK)
        == "integration origin/main · remote last fetched 3h ago"
    )
