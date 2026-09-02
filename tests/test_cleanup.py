"""Acceptance tests for the Cleanup preview and its performance.

Every test runs against a disposable repository on ``main`` whose ``origin``
is a path that is never fetched; Remote-Tracking Branches and ``origin/HEAD``
are written with ``update-ref`` so nothing talks to the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from dashpot.cleanup import (
    CHANGED_SINCE_PREVIEW,
    BranchCleanupRequest,
    CleanupConfirmation,
    CleanupPreview,
    CleanupRequest,
    CleanupTarget,
    WorktreeCleanupRequest,
    describe_cleanup_preview,
    describe_cleanup_report,
    inspect_cleanup,
    perform_cleanup,
)
from dashpot.commands import CommandResult, run_command
from dashpot.git import Git, GitError
from dashpot.hook_records import session_directory, write_hook_record
from dashpot.processes import ProcessIdentity, ProcessLookup, host_process_lookup
from dashpot.repository import LockHolderProbe
from dashpot.serialization import (
    cleanup_preview_document,
    cleanup_report_document,
)
from dashpot.worktrees import check_worktree
from factories import git
from helpers import table_lookup


def repo(tmp_path: Path, *, origin: bool = True) -> Path:
    """A repository on ``main`` with one commit, and an origin it never fetches."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "sim@example.invalid")
    git(root, "config", "user.name", "Sim")
    (root / "README.md").write_text("Sim\n")
    (root / ".gitignore").write_text(".venv/\n.dashpot/state/\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    if origin:
        git(root, "remote", "add", "origin", str(tmp_path / "never-fetched.git"))
        track(root, "main", "main")
        git(
            root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"
        )
    return root


def commit(root: Path, message: str, path: str = "work.txt") -> str:
    (root / path).write_text(f"{message}\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def branch(root: Path, name: str, *, commits: int = 1) -> str:
    """A Branch off ``main`` with ``commits`` commits; ``main`` stays checked out."""
    git(root, "checkout", "-q", "-b", name)
    tip = git(root, "rev-parse", "HEAD")
    for index in range(commits):
        tip = commit(root, f"{name} {index}", path=f"{name}.txt")
    git(root, "checkout", "-q", "main")
    return tip


def track(root: Path, name: str, ref: str, remote: str = "origin") -> None:
    git(root, "update-ref", f"refs/remotes/{remote}/{name}", ref)


def integrate(root: Path, name: str) -> None:
    """Fast-forward ``main`` and ``origin/main`` onto the Branch."""
    git(root, "merge", "-q", "--ff-only", name)
    track(root, "main", "main")


def preview_branch(root: Path, name: str) -> CleanupPreview:
    return inspect_cleanup(BranchCleanupRequest(root, name))


def by_identity(preview: CleanupPreview) -> dict[str, CleanupTarget]:
    return {target.identity: target for target in preview.targets}


def kinds(target: CleanupTarget) -> set[str]:
    return {blocker.kind for blocker in target.blockers}


# --- Branch targets ---------------------------------------------------------


def test_integrated_local_and_remote_targets_are_available(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", "feat")

    preview = preview_branch(root, "feat")

    assert preview.kind == "branch"
    assert preview.subject == "feat"
    assert preview.anchor == str(root.resolve())
    assert preview.refusals == ()
    targets = by_identity(preview)
    assert list(targets) == ["local:refs/heads/feat", "remote:origin:refs/heads/feat"]
    local = targets["local:refs/heads/feat"]
    assert local.kind == "local-branch"
    assert local.available is True
    assert local.expected == tip
    assert local.integration is not None
    assert local.integration.state == "integrated"
    assert local.integration.integration_ref == "refs/remotes/origin/main"
    assert local.consequences == (
        f"deletes refs/heads/feat at {tip[:7]}; recreate with: git branch feat {tip}",
    )
    remote = targets["remote:origin:refs/heads/feat"]
    assert remote.kind == "remote-branch"
    assert remote.remote == "origin"
    assert remote.ref == "refs/remotes/origin/feat"
    assert remote.available is True
    assert remote.expected == tip
    assert remote.observed_at is None
    assert remote.consequences[0] == (
        f"deletes feat at origin, leased on refs/remotes/origin/feat at {tip[:7]}; "
        f"recreate with: git push origin {tip}:refs/heads/feat"
    )
    assert preview.selectable == (local, remote)
    assert len(preview.fingerprint) == 16


def test_unintegrated_branch_is_blocked_with_the_log_command(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat", commits=2)

    target = by_identity(preview_branch(root, "feat"))["local:refs/heads/feat"]

    assert target.available is False
    assert target.integration is not None
    assert target.integration.state == "unintegrated"
    assert target.integration.unintegrated_commits == 2
    (blocker,) = target.blockers
    assert blocker.kind == "unintegrated"
    assert blocker.detail == "2 commit(s) not reachable from refs/remotes/origin/main"
    assert (
        blocker.command == "git log --oneline refs/remotes/origin/main..refs/heads/feat"
    )


def test_content_integrated_branch_is_available_with_its_warning(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    git(root, "merge", "-q", "--squash", "feat")
    git(root, "commit", "-q", "-m", "feat (squashed)")
    track(root, "main", "main")

    target = by_identity(preview_branch(root, "feat"))["local:refs/heads/feat"]

    assert target.available is True
    assert target.integration is not None
    assert target.integration.state == "content-integrated"
    assert target.consequences[1] == (
        "content is integrated, but 1 original commit(s) are not reachable from "
        "refs/remotes/origin/main and lose their last named ref"
    )


def test_the_integration_branch_is_never_a_target(tmp_path: Path) -> None:
    root = repo(tmp_path)

    git(root, "remote", "add", "upstream", str(tmp_path / "upstream.git"))
    track(root, "main", "main", remote="upstream")

    targets = by_identity(preview_branch(root, "main"))

    # The local main is checked out at the root as well; both facts are shown.
    assert kinds(targets["local:refs/heads/main"]) == {
        "integration-branch",
        "checked-out",
    }
    assert kinds(targets["remote:origin:refs/heads/main"]) == {"integration-branch"}
    assert kinds(targets["remote:upstream:refs/heads/main"]) == {"integration-branch"}
    assert targets["local:refs/heads/main"].blockers[0].detail == (
        "refs/heads/main carries the Integration Branch's name "
        "(refs/remotes/origin/main)"
    )
    assert targets["remote:origin:refs/heads/main"].blockers[0].detail == (
        "refs/remotes/origin/main is the Integration Branch"
    )


def test_checked_out_branch_names_its_worktree(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")

    target = by_identity(preview_branch(root, "feat"))["local:refs/heads/feat"]

    (blocker,) = target.blockers
    assert blocker.kind == "checked-out"
    assert blocker.detail == (
        f"checked out at {worktree.resolve()}; remove that Worktree first"
    )


def test_remote_only_branch_yields_one_remote_target(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)
    git(root, "branch", "-D", "feat")

    preview = preview_branch(root, "feat")

    (target,) = preview.targets
    assert target.identity == "remote:origin:refs/heads/feat"
    assert target.available is True


def test_non_canonical_mapping_and_several_push_urls_block_the_remote(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)
    git(
        root,
        "config",
        "remote.origin.fetch",
        "+refs/heads/main:refs/remotes/origin/main",
    )
    git(root, "remote", "set-url", "--add", "--push", "origin", "git@example.invalid:a")
    git(root, "remote", "set-url", "--add", "--push", "origin", "git@example.invalid:b")

    target = by_identity(preview_branch(root, "feat"))["remote:origin:refs/heads/feat"]

    assert kinds(target) == {"remote-mapping", "push-url"}
    by_kind = {blocker.kind: blocker for blocker in target.blockers}
    assert "+refs/heads/main:refs/remotes/origin/main rather than the canonical" in (
        by_kind["remote-mapping"].detail
    )
    assert by_kind["push-url"].detail.startswith("remote origin has 2 push URLs")


def test_every_remote_is_its_own_target(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    git(root, "remote", "add", "upstream", str(tmp_path / "upstream.git"))
    track(root, "feat", tip)
    track(root, "feat", tip, remote="upstream")

    preview = preview_branch(root, "feat")

    assert [target.identity for target in preview.targets] == [
        "local:refs/heads/feat",
        "remote:origin:refs/heads/feat",
        "remote:upstream:refs/heads/feat",
    ]
    assert all(target.available for target in preview.targets)


def test_an_unknown_branch_is_a_refusal(tmp_path: Path) -> None:
    root = repo(tmp_path)

    preview = preview_branch(root, "nope")

    assert preview.targets == ()
    assert preview.refusals == (f"no Branch named nope at {root.resolve()}",)
    assert preview.selectable == ()


def test_without_an_integration_branch_the_gate_is_unknown(tmp_path: Path) -> None:
    root = repo(tmp_path, origin=False)
    branch(root, "feat")
    git(root, "branch", "master", "main")

    target = by_identity(preview_branch(root, "feat"))["local:refs/heads/feat"]

    assert target.integration is not None
    assert target.integration.state == "unknown"
    (blocker,) = target.blockers
    assert blocker.kind == "unknown-integration"
    assert blocker.detail.startswith("no Integration Branch could be chosen")


def test_fingerprint_follows_the_observed_facts(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    before = preview_branch(root, "feat")

    assert preview_branch(root, "feat").fingerprint == before.fingerprint
    git(root, "checkout", "-q", "feat")
    commit(root, "more")
    git(root, "checkout", "-q", "main")
    after = preview_branch(root, "feat")

    assert after.fingerprint != before.fingerprint
    assert after.targets[0].available is False


# --- Worktree targets -------------------------------------------------------


def preview_worktree(
    root: Path,
    path: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    protected: Sequence[Path] = (),
) -> CleanupPreview:
    return inspect_cleanup(
        WorktreeCleanupRequest(root, path),
        lookup=lookup,
        lock_probe=lock_probe,
        protected=protected,
    )


def test_clean_worktree_offers_removal_and_its_branch_separately(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    (worktree / ".venv").mkdir()
    (worktree / ".venv" / "bin").write_text("")

    preview = preview_worktree(root, worktree)

    resolved = worktree.resolve()
    assert preview.kind == "worktree"
    assert preview.subject == str(resolved)
    assert preview.ignored == (".venv/",)
    tree, local = preview.targets
    assert tree.identity == f"worktree:{resolved}"
    assert tree.kind == "worktree"
    assert tree.expected == tip
    assert tree.path == str(resolved)
    assert tree.available is True
    assert tree.consequences == (
        f"removes {resolved} with git worktree remove",
        "1 ignored path(s) inside it are deleted too, including any Dashpot state, "
        "hook records, and Work Store there",
        "the local Branch feat is retained unless selected as well",
    )
    assert local.identity == "local:refs/heads/feat"
    assert local.requires == tree.identity
    assert local.available is True
    assert local.consequences[0].startswith("after the Worktree is removed, deletes")


def test_dirty_locked_and_occupied_worktree_is_blocked(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    (worktree / "scratch.txt").write_text("")
    git(root, "worktree", "lock", "--reason", "claude pid 4242", str(worktree))
    live = ProcessIdentity(7777, 1, "claude", "Tue Aug 25 02:00:00 2026")
    write_hook_record(
        {
            "version": 2,
            "sessionId": "01c7192b-2990-4f83-ad33-290ac22eb4d1",
            "harness": "claude-code",
            "state": "running",
            "cwd": str(worktree),
            "repositoryRoot": str(worktree),
            "branch": "feat",
            "event": "UserPromptSubmit",
            "lastActivityAt": "2026-08-30T03:40:00.000000Z",
            "sessionProcess": live.as_record(),
        },
        session_directory(worktree),
    )

    preview = preview_worktree(
        root,
        worktree,
        lookup=table_lookup({live.pid: live}),
        lock_probe=lambda _pid: "gone",
    )

    tree, local = preview.targets
    assert kinds(tree) == {"dirty", "locked", "agent-session"}
    assert tree.available is False
    # The Branch's own gate is independent of the Worktree's state.
    assert kinds(local) == {"unintegrated"}
    assert preview.selectable == ()


def test_protected_and_main_worktrees_are_never_removable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")

    protected = preview_worktree(root, worktree, protected=[worktree])
    main = preview_worktree(root, root)

    assert kinds(protected.targets[0]) == {"protected"}
    assert kinds(main.targets[0]) == {"main-worktree"}
    assert main.targets[1].identity == "local:refs/heads/main"
    assert kinds(main.targets[1]) == {"integration-branch"}


def test_detached_worktree_needs_a_durable_ref(tmp_path: Path) -> None:
    root = repo(tmp_path)
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", "--detach", str(worktree), "main")

    reachable = preview_worktree(root, worktree)
    lost = commit(worktree, "unreachable")
    unreachable = preview_worktree(root, worktree)

    (tree,) = reachable.targets
    assert tree.available is True
    assert tree.ref is None
    (tree,) = unreachable.targets
    (blocker,) = tree.blockers
    assert blocker.kind == "detached"
    assert blocker.detail == (
        f"detached at {lost[:7]}, which no local Branch, Remote-Tracking Branch, "
        f"or tag reaches"
    )
    assert blocker.command == f"git branch rescue/{lost[:7]} {lost}"
    report = check_worktree(root, worktree)
    assert [obstacle.kind for obstacle in report.obstacles] == ["detached"]


def test_missing_worktree_directory_is_unavailable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    (worktree / ".git").unlink()
    for child in worktree.iterdir():
        child.unlink()
    worktree.rmdir()

    preview = preview_worktree(root, worktree)

    assert kinds(preview.targets[0]) == {"unavailable"}
    assert preview.ignored == ()


def test_inspection_never_writes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    refs = git(root, "for-each-ref")
    worktrees = git(root, "worktree", "list", "--porcelain")

    preview_branch(root, "feat")
    preview_worktree(root, worktree)

    assert git(root, "for-each-ref") == refs
    assert git(root, "worktree", "list", "--porcelain") == worktrees
    assert git(root, "status", "--porcelain") == ""


# --- Contracts ----------------------------------------------------------


def test_json_document_key_sets_are_stable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)

    document = cleanup_preview_document(preview_branch(root, "feat"))

    assert set(document) == {
        "kind",
        "subject",
        "anchor",
        "targets",
        "ignored",
        "refusals",
        "fingerprint",
    }
    local, remote = document["targets"]
    assert set(local) == {
        "identity",
        "kind",
        "label",
        "expected",
        "ref",
        "remote",
        "path",
        "integration",
        "observedAt",
        "requires",
        "blockers",
        "consequences",
        "available",
    }
    assert set(local["integration"]) == {
        "integrationRef",
        "unintegratedCommits",
        "contentIntegrated",
        "state",
    }
    assert local["available"] is True
    assert remote["remote"] == "origin"


def test_describe_renders_each_target_with_its_gate(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat", commits=1)

    lines = describe_cleanup_preview(preview_branch(root, "feat"))
    tip = git(root, "rev-parse", "feat")

    assert lines[0] == "Delete Branch   feat"
    assert lines[1] == f"Repository      {root.resolve()}"
    assert lines[2] == "Targets"
    assert lines[3] == f"  [ ] Local Branch refs/heads/feat @ {tip[:7]} — unavailable"
    assert lines[4] == "      ↑ commits are not reachable from the Integration Branch"
    assert lines[5] == (
        "      blocked: unintegrated: 1 commit(s) not reachable from "
        "refs/remotes/origin/main"
    )
    assert lines[6] == (
        "          run: git log --oneline refs/remotes/origin/main..refs/heads/feat"
    )
    assert lines[7].startswith("      → deletes refs/heads/feat at")


def test_a_runner_failure_is_never_read_as_absence(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")

    def failing(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        raise OSError("git is missing")

    with pytest.raises(GitError, match="git is missing"):
        inspect_cleanup(BranchCleanupRequest(root, "feat"), git=Git(root, 5, failing))


# --- Performing -----------------------------------------------------------


def confirm(
    request: CleanupRequest,
    preview: CleanupPreview,
    *identities: str,
    delete_ignored: bool = False,
) -> CleanupConfirmation:
    return CleanupConfirmation(
        request, preview.fingerprint, identities, delete_ignored=delete_ignored
    )


def linked(tmp_path: Path, root: Path, name: str) -> Path:
    """A clean linked Worktree on ``name`` with one ignored path inside."""
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), name)
    (worktree / ".venv").mkdir()
    (worktree / ".venv" / "bin").write_text("")
    return worktree


def test_deleting_a_local_branch_removes_its_ref_and_configuration(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)
    git(root, "config", "branch.feat.remote", "origin")
    git(root, "config", "branch.feat.merge", "refs/heads/feat")
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)

    report = perform_cleanup(confirm(request, preview, "local:refs/heads/feat"))

    assert report.performed is True
    assert report.succeeded is True
    assert report.changed is False
    (result,) = report.results
    assert result.outcome == "deleted"
    assert result.detail == f"deleted refs/heads/feat at {tip[:7]}"
    assert result.recovery == f"git branch feat {tip}"
    assert git(root, "for-each-ref", "refs/heads/feat") == ""
    assert "branch.feat" not in git(root, "config", "--list")
    # The Remote-Tracking Branch is the remote target's business, not this one's.
    assert git(root, "rev-parse", "refs/remotes/origin/feat") == tip
    assert git(root, "rev-parse", "main") == tip


def test_a_changed_preview_performs_nothing_and_returns_the_fresh_one(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    request = BranchCleanupRequest(root, "feat")
    stale = inspect_cleanup(request)
    git(root, "checkout", "-q", "feat")
    commit(root, "late", path="late.txt")
    git(root, "checkout", "-q", "main")

    report = perform_cleanup(confirm(request, stale, "local:refs/heads/feat"))

    assert report.performed is False
    assert report.changed is True
    assert report.succeeded is False
    assert report.refusals == (CHANGED_SINCE_PREVIEW,)
    assert report.preview.fingerprint != stale.fingerprint
    assert report.preview.target("local:refs/heads/feat") is not None
    assert git(root, "rev-parse", "--verify", "refs/heads/feat")


def test_a_selection_the_preview_does_not_allow_is_refused(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    branch(root, "done")
    integrate(root, "done")
    worktree = linked(tmp_path, root, "done")

    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)
    report = perform_cleanup(confirm(request, preview, "local:refs/heads/feat"))
    assert report.performed is False
    assert report.refusals == (
        "Local Branch is unavailable: 1 commit(s) not reachable from "
        "refs/remotes/origin/main",
    )
    assert git(root, "rev-parse", "refs/heads/feat") == tip

    assert perform_cleanup(confirm(request, preview)).refusals == (
        "no target is selected",
    )
    assert perform_cleanup(
        confirm(request, preview, "local:refs/heads/x")
    ).refusals == ("local:refs/heads/x is not a target of this preview",)

    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)
    tree, local = preview.targets
    assert perform_cleanup(confirm(request, preview, local.identity)).refusals == (
        f"Local Branch can only be deleted together with {tree.identity}",
    )
    assert perform_cleanup(confirm(request, preview, tree.identity)).refusals == (
        "removing the Worktree deletes 1 ignored path(s) inside it, which must be "
        "acknowledged",
    )
    assert worktree.exists()
    assert git(root, "rev-parse", "--verify", "refs/heads/done")


def serve(tmp_path: Path, root: Path, *names: str) -> Path:
    """Turn ``origin`` into a bare repository on disk holding ``main`` and ``names``."""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")
    git(root, "remote", "set-url", "origin", str(bare))
    git(root, "push", "-q", "origin", "main", *names)
    return bare


def served_feature(tmp_path: Path) -> tuple[Path, Path, str]:
    """A repository whose integrated ``feat`` is also at a served ``origin``."""
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    bare = serve(tmp_path, root, "feat")
    return root, bare, tip


def test_deleting_at_the_remote_is_leased_and_drops_the_tracking_ref(
    tmp_path: Path,
) -> None:
    root, bare, tip = served_feature(tmp_path)
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)
    assert preview.target("remote:origin:refs/heads/feat") is not None

    report = perform_cleanup(
        confirm(
            request, preview, "local:refs/heads/feat", "remote:origin:refs/heads/feat"
        )
    )

    assert report.succeeded is True
    remote, local = report.results
    assert (remote.kind, remote.outcome) == ("remote-branch", "deleted")
    assert remote.detail == (
        f"deleted feat at origin, which was at {tip[:7]}; Git dropped "
        f"refs/remotes/origin/feat"
    )
    assert remote.recovery == f"git push origin {tip}:refs/heads/feat"
    assert (local.kind, local.outcome) == ("local-branch", "deleted")
    assert git(bare, "for-each-ref", "refs/heads/feat") == ""
    assert git(bare, "rev-parse", "main") == tip
    assert git(root, "for-each-ref", "refs/remotes/origin/feat") == ""
    assert git(root, "for-each-ref", "refs/heads/feat") == ""


def test_a_remote_that_moved_refuses_the_lease_and_halts_the_local(
    tmp_path: Path,
) -> None:
    root, bare, tip = served_feature(tmp_path)
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(bare), str(other))
    git(other, "config", "user.email", "sim@example.invalid")
    git(other, "config", "user.name", "Sim")
    git(other, "checkout", "-q", "feat")
    commit(other, "elsewhere", path="elsewhere.txt")
    git(other, "push", "-q", "origin", "feat")
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)

    report = perform_cleanup(
        confirm(
            request, preview, "local:refs/heads/feat", "remote:origin:refs/heads/feat"
        )
    )

    assert report.succeeded is False
    remote, local = report.results
    assert remote.outcome == "refused"
    assert remote.detail == (
        f"origin no longer has feat at the leased {tip[:7]}: it moved since the "
        f"last fetch; fetch and confirm against the revised preview"
    )
    assert local.outcome == "refused"
    assert local.detail == "not attempted: Branch at origin was refused"
    assert git(bare, "rev-parse", "feat") != tip
    assert git(root, "rev-parse", "refs/heads/feat") == tip
    assert git(root, "rev-parse", "refs/remotes/origin/feat") == tip


def test_a_branch_already_gone_at_the_remote_is_already_absent(
    tmp_path: Path,
) -> None:
    root, bare, tip = served_feature(tmp_path)
    git(bare, "update-ref", "-d", "refs/heads/feat")
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)

    report = perform_cleanup(confirm(request, preview, "remote:origin:refs/heads/feat"))

    (remote,) = report.results
    assert remote.outcome == "already-absent"
    assert remote.detail == (
        "feat at origin was already gone; refs/remotes/origin/feat is stale until "
        "the next fetch prunes it"
    )
    assert report.succeeded is True
    # Nothing was fetched: the stale Remote-Tracking Branch is for ``f``.
    assert git(root, "rev-parse", "refs/remotes/origin/feat") == tip


def test_an_unreachable_remote_is_refused_with_gits_reason(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)

    report = perform_cleanup(
        confirm(
            request, preview, "local:refs/heads/feat", "remote:origin:refs/heads/feat"
        )
    )

    remote, local = report.results
    assert remote.outcome == "refused"
    assert remote.detail.startswith("fatal: ")
    assert local.detail == "not attempted: Branch at origin was refused"
    assert git(root, "rev-parse", "refs/heads/feat") == tip


def test_a_push_that_does_not_answer_is_unknown(tmp_path: Path) -> None:
    root, _bare, tip = served_feature(tmp_path)
    request = BranchCleanupRequest(root, "feat")

    def hanging(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if args[1] == "push":
            raise RuntimeError("timed out after 5.0s")
        return run_command(args, cwd, timeout)

    git_ = Git(root, 5, hanging)
    preview = inspect_cleanup(request, git=git_)
    report = perform_cleanup(
        confirm(
            request, preview, "remote:origin:refs/heads/feat", "local:refs/heads/feat"
        ),
        git=git_,
    )

    remote, local = report.results
    assert remote.outcome == "unknown"
    assert remote.detail == (
        "git push did not complete: timed out after 5.0s; check with: "
        "git ls-remote --heads origin refs/heads/feat; a surviving "
        "refs/remotes/origin/feat is pruned by the next fetch"
    )
    assert remote.recovery == f"git push origin {tip}:refs/heads/feat"
    assert local.detail == "not attempted: Branch at origin was unknown"
    assert git(root, "rev-parse", "refs/heads/feat") == tip


def test_a_stale_lease_whose_remote_does_not_answer_stays_refused(
    tmp_path: Path,
) -> None:
    root, bare, _tip = served_feature(tmp_path)
    git(bare, "update-ref", "-d", "refs/heads/feat")
    request = BranchCleanupRequest(root, "feat")

    def deaf(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if args[1] == "ls-remote":
            raise OSError("no route")
        return run_command(args, cwd, timeout)

    git_ = Git(root, 5, deaf)
    preview = inspect_cleanup(request, git=git_)
    report = perform_cleanup(
        confirm(request, preview, "remote:origin:refs/heads/feat"), git=git_
    )

    (remote,) = report.results
    assert remote.outcome == "refused"
    assert remote.detail.startswith("! [rejected]")
    assert remote.detail.endswith("(delete) -> feat (stale info)")


def test_removing_a_worktree_then_its_branch(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)
    tree, local = preview.targets

    report = perform_cleanup(
        confirm(request, preview, local.identity, tree.identity, delete_ignored=True)
    )

    assert report.succeeded is True
    first, second = report.results
    assert (first.kind, first.outcome) == ("worktree", "deleted")
    assert first.detail == f"removed {worktree.resolve()}"
    assert first.recovery == f"git worktree add {worktree.resolve()} feat"
    assert (second.kind, second.outcome) == ("local-branch", "deleted")
    assert second.recovery == f"git branch feat {tip}"
    assert not worktree.exists()
    assert git(root, "for-each-ref", "refs/heads/feat") == ""
    assert len(git(root, "worktree", "list", "--porcelain").split("\n\n")) == 1


def test_a_refused_removal_leaves_the_branch_unattempted(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)

    def refusing(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if list(args[1:3]) == ["worktree", "remove"]:
            return CommandResult(list(args), 128, "", "fatal: validation failed\n")
        return run_command(args, cwd, timeout)

    git_ = Git(root, 5, refusing)
    preview = inspect_cleanup(request, git=git_)
    tree, local = preview.targets
    report = perform_cleanup(
        confirm(request, preview, tree.identity, local.identity, delete_ignored=True),
        git=git_,
    )

    assert report.succeeded is False
    first, second = report.results
    assert first.outcome == "refused"
    assert first.detail == "fatal: validation failed"
    assert second.outcome == "refused"
    assert second.detail == "not attempted: Worktree was refused"
    assert worktree.exists()
    assert git(root, "rev-parse", "--verify", "refs/heads/feat")


def test_a_runner_failure_while_performing_is_unknown(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)

    def hanging(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if list(args[1:3]) == ["worktree", "remove"]:
            raise RuntimeError("timed out after 5.0s")
        return run_command(args, cwd, timeout)

    git_ = Git(root, 5, hanging)
    preview = inspect_cleanup(request, git=git_)
    tree, local = preview.targets
    report = perform_cleanup(
        confirm(request, preview, tree.identity, local.identity, delete_ignored=True),
        git=git_,
    )

    first, second = report.results
    assert first.outcome == "unknown"
    assert first.detail == (
        "git worktree remove did not complete: timed out after 5.0s; check with: "
        "git worktree list"
    )
    assert second.detail == "not attempted: Worktree was unknown"
    assert report.succeeded is False


def test_a_target_gone_by_the_time_git_answers_is_already_absent(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    request = BranchCleanupRequest(root, "feat")

    def racing(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        result = run_command(args, cwd, timeout)
        if list(args[1:3]) == ["update-ref", "-d"]:
            # The deletion landed, yet Git's answer was lost: only the ref
            # itself can say whether the target is still there.
            return CommandResult(list(args), 1, "", "error: lost\n")
        return result

    preview = inspect_cleanup(request)
    report = perform_cleanup(
        confirm(request, preview, "local:refs/heads/feat"), git=Git(root, 5, racing)
    )

    (result,) = report.results
    assert result.outcome == "already-absent"
    assert result.detail == "refs/heads/feat was already gone"
    assert report.succeeded is True


def test_a_dry_run_plans_in_order_and_changes_nothing(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)
    tree, local = preview.targets
    refs = git(root, "for-each-ref")

    report = perform_cleanup(
        confirm(request, preview, local.identity, tree.identity, delete_ignored=True),
        dry_run=True,
    )

    assert report.dry_run is True
    assert report.performed is False
    assert report.succeeded is False
    assert report.refusals == ()
    assert report.planned == (tree.identity, local.identity)
    assert report.results == ()
    assert worktree.exists()
    assert git(root, "for-each-ref") == refs

    lines = describe_cleanup_report(report)
    assert lines[0] == f"Remove Worktree {worktree.resolve()}"
    assert lines[2] == "Dry run         would attempt, in order"
    assert lines[3] == f"  1. Worktree {worktree.resolve()}"
    assert lines[4] == "  2. Local Branch refs/heads/feat"


def test_report_json_key_sets_and_description_are_stable(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)

    report = perform_cleanup(confirm(request, preview, "local:refs/heads/feat"))

    document = cleanup_report_document(report)
    assert set(document) == {
        "kind",
        "subject",
        "anchor",
        "dryRun",
        "performed",
        "preview",
        "changed",
        "refusals",
        "planned",
        "results",
        "succeeded",
    }
    (result,) = document["results"]
    assert set(result) == {
        "identity",
        "kind",
        "label",
        "expected",
        "outcome",
        "detail",
        "recovery",
    }
    assert set(document["preview"]) == set(cleanup_preview_document(preview))

    lines = describe_cleanup_report(report)
    assert lines[0] == "Delete Branch   feat"
    assert lines[1] == f"Repository      {root.resolve()}"
    assert lines[2] == "Results"
    assert lines[3] == f"  deleted        Local Branch refs/heads/feat @ {tip[:7]}"
    assert lines[4] == f"      deleted refs/heads/feat at {tip[:7]}"
    assert lines[5] == f"      recover: git branch feat {tip}"

    changed = perform_cleanup(confirm(request, preview, "local:refs/heads/feat"))
    lines = describe_cleanup_report(changed)
    assert lines[2] == f"Changed         {CHANGED_SINCE_PREVIEW}"
    assert lines[3].startswith("Refused         no Branch named feat at ")
