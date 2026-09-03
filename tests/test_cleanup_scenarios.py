"""Acceptance scenarios for Cleanup, in the shapes real Issue Worktrees take.

Each scenario builds a disposable Repository with a linked Worktree in one of
the shapes the Cleanup series was planned against — a finished Issue whose
Branch the forge deleted after a squash merge, a merged Branch still at
``origin``, a pushed but unintegrated Branch, a second approach with commits
of its own, and a dirty Worktree on a Branch named unlike its directory — and
drives it through the same Git-backed adapter the dashboard's ``x`` key uses,
asserting what the preview offers, what confirmation performs, and what is
left behind. Only the served ``origin`` is a bare repository on disk; nothing
talks to the network.
"""

from __future__ import annotations

from pathlib import Path

from dashpot.cleanup import (
    BranchCleanupRequest,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    CleanupTarget,
    GitCleanupAdapter,
    TargetKind,
    WorktreeCleanupRequest,
)
from factories import git
from test_cleanup import branch, commit, integrate, linked, repo, serve, track

ADAPTER = GitCleanupAdapter(timeout=30.0)


def target(preview: CleanupPreview, kind: TargetKind) -> CleanupTarget:
    """The one target of ``kind`` in the preview."""
    (found,) = [item for item in preview.targets if item.kind == kind]
    return found


def confirm(
    request: CleanupRequest,
    preview: CleanupPreview,
    *targets: CleanupTarget,
    ignored: bool = False,
) -> CleanupConfirmation:
    return CleanupConfirmation(
        request,
        preview.fingerprint,
        tuple(item.identity for item in targets),
        delete_ignored=ignored,
    )


def squash_merge(root: Path, name: str, message: str) -> None:
    """Land ``name`` on ``main`` the way a forge's squash merge does, and fetch it."""
    git(root, "merge", "-q", "--squash", name)
    git(root, "commit", "-q", "-m", message)
    track(root, "main", "main")


def refs(root: Path) -> set[str]:
    return set(git(root, "for-each-ref", "--format=%(refname)").split())


def worktree_paths(root: Path) -> set[str]:
    return {
        line.removeprefix("worktree ")
        for line in git(root, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    }


def outcomes(report: CleanupReport) -> list[tuple[str, str]]:
    return [(result.label, result.outcome) for result in report.results]


def test_finished_issue_whose_branch_the_forge_deleted_after_a_squash(
    tmp_path: Path,
) -> None:
    """The Worktree goes, the local Branch goes, and origin's copy is already absent."""
    root = repo(tmp_path)
    branch(root, "66-finished", commits=2)
    bare = serve(tmp_path, root, "66-finished")
    worktree = linked(tmp_path, root, "66-finished")
    squash_merge(root, "66-finished", "Finish the Issue (#66)")
    # The forge deleted the Branch when the PR merged; nothing has fetched since.
    git(bare, "branch", "-D", "66-finished")
    assert "refs/remotes/origin/66-finished" in refs(root)

    preview_request = WorktreeCleanupRequest(root, worktree)
    preview = ADAPTER.inspect(preview_request, protected=(root,))
    tree, local = target(preview, "worktree"), target(preview, "local-branch")
    assert (tree.available, local.available) == (True, True)
    assert local.integration is not None
    assert local.integration.state == "content-integrated"
    assert local.requires == tree.identity
    assert preview.ignored == (".venv/",)

    report = ADAPTER.perform(
        confirm(preview_request, preview, tree, local, ignored=True), protected=(root,)
    )

    assert report.succeeded is True
    assert outcomes(report) == [("Worktree", "deleted"), ("Local Branch", "deleted")]
    assert str(worktree) not in worktree_paths(root)
    assert not worktree.exists()
    assert "refs/heads/66-finished" not in refs(root)

    # The Remote-Tracking Branch still stands for a Branch that is gone: the
    # leased delete push is rejected, and one read-only ls-remote says why.
    remote_preview_request = BranchCleanupRequest(root, "66-finished")
    remote_preview = ADAPTER.inspect(remote_preview_request, protected=(root,))
    remote = target(remote_preview, "remote-branch")
    assert remote.available is True
    remote_report = ADAPTER.perform(
        confirm(remote_preview_request, remote_preview, remote), protected=(root,)
    )

    assert remote_report.succeeded is True
    assert outcomes(remote_report) == [("Branch at origin", "already-absent")]
    assert "refs/remotes/origin/66-finished" in refs(root), "stale until a fetch prunes"


def test_merged_issue_whose_branch_is_still_at_origin(tmp_path: Path) -> None:
    """Origin's copy is deleted under its lease and its tracking ref goes with it."""
    root = repo(tmp_path)
    tip = branch(root, "96-merged")
    serve(tmp_path, root, "96-merged")
    worktree = linked(tmp_path, root, "96-merged")
    integrate(root, "96-merged")

    preview_request = WorktreeCleanupRequest(root, worktree)
    preview = ADAPTER.inspect(preview_request, protected=(root,))
    tree, local = target(preview, "worktree"), target(preview, "local-branch")
    assert local.integration is not None
    assert local.integration.state == "integrated"
    report = ADAPTER.perform(
        confirm(preview_request, preview, tree, local, ignored=True), protected=(root,)
    )
    assert outcomes(report) == [("Worktree", "deleted"), ("Local Branch", "deleted")]
    assert [result.recovery for result in report.results] == [
        f"git worktree add {worktree} 96-merged",
        f"git branch 96-merged {tip}",
    ]

    remote_preview_request = BranchCleanupRequest(root, "96-merged")
    remote_preview = ADAPTER.inspect(remote_preview_request, protected=(root,))
    assert [item.kind for item in remote_preview.targets] == ["remote-branch"]
    remote_report = ADAPTER.perform(
        confirm(
            remote_preview_request,
            remote_preview,
            target(remote_preview, "remote-branch"),
        ),
        protected=(root,),
    )

    assert outcomes(remote_report) == [("Branch at origin", "deleted")]
    assert "refs/remotes/origin/96-merged" not in refs(root)
    assert "96-merged" not in git(root, "ls-remote", "--heads", "origin")
    gone_request = BranchCleanupRequest(root, "96-merged")
    gone = ADAPTER.inspect(gone_request, protected=(root,))
    assert gone.targets == ()
    assert gone.refusals == (f"no Branch named 96-merged at {root}",)


def test_pushed_but_unintegrated_work_loses_its_worktree_and_keeps_its_branch(
    tmp_path: Path,
) -> None:
    """Removing the Worktree retains the Branch; the Branch itself is offered nowhere."""
    root = repo(tmp_path)
    tip = branch(root, "85-pydantic", commits=3)
    serve(tmp_path, root, "85-pydantic")
    worktree = linked(tmp_path, root, "85-pydantic")

    preview_request = WorktreeCleanupRequest(root, worktree)
    preview = ADAPTER.inspect(preview_request, protected=(root,))
    tree, local = target(preview, "worktree"), target(preview, "local-branch")

    assert tree.available is True
    assert tree.consequences[-1] == (
        "the local Branch 85-pydantic is retained unless selected as well"
    )
    assert local.available is False
    assert [blocker.kind for blocker in local.blockers] == ["unintegrated"]
    assert local.blockers[0].command == (
        "git log --oneline refs/remotes/origin/main..refs/heads/85-pydantic"
    )
    assert [item.identity for item in preview.selectable] == [tree.identity]

    # A selection the preview does not allow is refused, not performed.
    both = ADAPTER.perform(
        confirm(preview_request, preview, tree, local, ignored=True), protected=(root,)
    )
    assert both.performed is False
    assert both.refusals == (
        "Local Branch is unavailable: 3 commit(s) not reachable from "
        "refs/remotes/origin/main",
    )
    assert str(worktree) in worktree_paths(root)

    alone = ADAPTER.perform(
        confirm(preview_request, preview, tree, ignored=True), protected=(root,)
    )
    assert outcomes(alone) == [("Worktree", "deleted")]
    assert not worktree.exists()
    assert git(root, "rev-parse", "refs/heads/85-pydantic") == tip

    at_origin_request = BranchCleanupRequest(root, "85-pydantic")
    at_origin = ADAPTER.inspect(at_origin_request, protected=(root,))
    assert {item.kind for item in at_origin.targets} == {
        "local-branch",
        "remote-branch",
    }
    assert at_origin.selectable == ()


def test_a_second_approach_with_commits_of_its_own_keeps_them_on_its_branch(
    tmp_path: Path,
) -> None:
    """Two Worktrees on one Issue: each goes on its own, and unpushed work stays named."""
    root = repo(tmp_path)
    branch(root, "85-issue-profile")
    serve(tmp_path, root, "85-issue-profile")
    integrate(root, "85-issue-profile")
    finished = linked(tmp_path, root, "85-issue-profile")
    git(root, "branch", "-q", "85-issue-profile-2", "main")
    second = tmp_path / "wt-2"
    git(root, "worktree", "add", "-q", str(second), "85-issue-profile-2")
    tip = commit(second, "second approach", path="profile.py")

    preview_request = WorktreeCleanupRequest(root, second)
    preview = ADAPTER.inspect(preview_request, protected=(root,))
    tree, local = target(preview, "worktree"), target(preview, "local-branch")
    assert tree.available is True
    assert local.available is False
    assert [blocker.kind for blocker in local.blockers] == ["unintegrated"]

    other_request = WorktreeCleanupRequest(root, finished)
    other = ADAPTER.inspect(other_request, protected=(root,))
    report = ADAPTER.perform(
        confirm(
            other_request,
            other,
            target(other, "worktree"),
            target(other, "local-branch"),
            ignored=True,
        ),
        protected=(root,),
    )
    assert outcomes(report) == [("Worktree", "deleted"), ("Local Branch", "deleted")]
    assert worktree_paths(root) == {str(root), str(second)}

    second_report = ADAPTER.perform(
        confirm(preview_request, preview, tree), protected=(root,)
    )
    assert outcomes(second_report) == [("Worktree", "deleted")]
    assert worktree_paths(root) == {str(root)}
    assert git(root, "rev-parse", "refs/heads/85-issue-profile-2") == tip


def test_a_dirty_worktree_on_a_branch_named_unlike_it_halts_before_its_branch(
    tmp_path: Path,
) -> None:
    """A dirty Worktree is refused unforced, and its Branch is never deletable alone."""
    root = repo(tmp_path)
    branch(root, "agents-md-hold-issue-work")
    serve(tmp_path, root, "agents-md-hold-issue-work")
    worktree = tmp_path / "85-adopt-pydantic"
    git(root, "worktree", "add", "-q", str(worktree), "agents-md-hold-issue-work")
    squash_merge(root, "agents-md-hold-issue-work", "Hold Issue work (#85)")
    (worktree / "AGENTS.md").write_text("edited after the merge\n")

    preview_request = WorktreeCleanupRequest(root, worktree)
    preview = ADAPTER.inspect(preview_request, protected=(root,))
    tree, local = target(preview, "worktree"), target(preview, "local-branch")
    assert tree.available is False
    assert [blocker.kind for blocker in tree.blockers] == ["dirty"]
    # The Branch is integrated by content, but a Worktree that cannot go
    # keeps it checked out: nothing here is selectable.
    assert local.available is False
    assert local.integration is not None
    assert local.integration.state == "content-integrated"
    assert local.requires == tree.identity
    assert [blocker.kind for blocker in local.blockers] == ["checked-out"]
    assert local.blockers[0].detail == (
        f"checked out at {worktree}, whose removal is blocked"
    )
    assert preview.selectable == ()

    alone = ADAPTER.perform(confirm(preview_request, preview, local), protected=(root,))
    assert alone.performed is False
    assert alone.refusals == (
        f"Local Branch is unavailable: {local.blockers[0].detail}",
    )

    together = ADAPTER.perform(
        confirm(preview_request, preview, tree, local), protected=(root,)
    )
    assert together.performed is False
    assert together.refusals == (
        f"Worktree is unavailable: {tree.blockers[0].detail}",
        f"Local Branch is unavailable: {local.blockers[0].detail}",
    )

    # From the Branches pane the same Branch is refused as checked out there.
    from_branch_request = BranchCleanupRequest(root, "agents-md-hold-issue-work")
    from_branch = ADAPTER.inspect(from_branch_request, protected=(root,))
    checked_out = target(from_branch, "local-branch")
    assert checked_out.available is False
    assert [blocker.kind for blocker in checked_out.blockers] == ["checked-out"]
    assert str(worktree) in checked_out.blockers[0].detail
    assert str(worktree) in worktree_paths(root)
    assert "refs/heads/agents-md-hold-issue-work" in refs(root)
