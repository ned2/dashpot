"""Acceptance tests for the read-only Cleanup preview.

Every test runs against a disposable repository on ``main`` whose ``origin``
is a path that is never fetched; Remote-Tracking Branches and ``origin/HEAD``
are written with ``update-ref`` so nothing talks to the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from dashpot.cleanup import (
    BranchCleanupRequest,
    CleanupPreview,
    CleanupTarget,
    WorktreeCleanupRequest,
    describe_cleanup_preview,
    inspect_cleanup,
)
from dashpot.commands import CommandResult
from dashpot.git import Git, GitError
from dashpot.hook_records import session_directory, write_hook_record
from dashpot.processes import ProcessIdentity, ProcessLookup, host_process_lookup
from dashpot.repository import LockHolderProbe
from dashpot.serialization import cleanup_preview_document
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

    assert lines[0] == "Delete Branch  feat"
    assert lines[1] == f"Repository     {root.resolve()}"
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
