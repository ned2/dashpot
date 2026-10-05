"""Acceptance tests for the Cleanup preview and its performance.

Every test runs against a disposable repository on ``main`` whose ``origin``
is a path that is never fetched; Remote-Tracking Branches and ``origin/HEAD``
are written with ``update-ref`` so nothing talks to the network.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from contextvars import copy_context
from pathlib import Path

import pytest

from dashpot.core.commands import (
    CommandError,
    CommandResult,
    RunningCommands,
    non_interactive_runner,
    run_command,
)
from dashpot.core.git import Git, GitError
from dashpot.core.state_paths import ensure_state_directory
from dashpot.repository.cleanup import (
    CHANGED_SINCE_PREVIEW,
    SUB_AGENT_SCOPE,
    BranchCleanupRequest,
    CleanupBlocker,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    CleanupTarget,
    WorktreeCleanupRequest,
    default_choices,
    describe_cleanup_preview,
    describe_cleanup_report,
    inspect_cleanup,
    perform_cleanup,
)
from dashpot.repository.cleanup.adapter import GitCleanupAdapter
from dashpot.repository.cleanup.obstacles import (
    NO_INTEGRATION_BRANCH,
    assess_worktree_occupancy,
    counted,
)
from dashpot.repository.repository import LockHolderProbe, short_ref
from dashpot.repository.worktrees.removability import (
    check_worktree,
    describe_removability,
)
from dashpot.serialization import (
    cleanup_preview_document,
    cleanup_report_document,
    removability_document,
)
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.hook_records import (
    HookRecord,
    HookRecordStore,
    project_session_store,
    session_directory,
    state_directory,
)
from dashpot.sessions.processes import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
)
from dashpot.sessions.session_exits import SESSION_EXITS
from dashpot.sessions.work_store import ActiveWork, SessionProcess, WorkStore
from factories import git
from helpers import absent, scan_of, table_lookup, unobservable


def repo(tmp_path: Path, *, origin: bool = True, ignore_state: bool = True) -> Path:
    """A repository on ``main`` with one commit, and an origin it never fetches.

    Its ``.gitignore`` holds a rule for Dashpot state unless ``ignore_state``
    is false, as in a Project that never added one.
    """
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Sim\n")
    (root / ".gitignore").write_text(
        ".venv/\n.dashpot/state/\n" if ignore_state else ".venv/\n"
    )
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
    assert blocker.detail == "2 commits not reachable from origin/main"
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
        "content is integrated, but deleting it drops the last named ref to 1 "
        "original commit not reachable from origin/main"
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
        "main carries the Integration Branch's name (origin/main)"
    )
    assert targets["remote:origin:refs/heads/main"].blockers[0].detail == (
        "origin/main is the Integration Branch"
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


def test_a_remote_whose_push_url_git_cannot_report_has_no_destination(
    tmp_path: Path,
) -> None:
    """Git answers ``get-url`` with the remote's name even without a URL, so
    the zero case is Git refusing to answer at all."""
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)

    def urlless(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if args[1:4] == ["remote", "get-url", "--push"]:
            return CommandResult(
                list(args), 128, "", "fatal: No such remote 'origin'\n"
            )
        return run_command(args, cwd, timeout)

    preview = inspect_cleanup(
        BranchCleanupRequest(root, "feat"), git=Git(root, 5, urlless)
    )
    target = by_identity(preview)["remote:origin:refs/heads/feat"]

    assert kinds(target) == {"push-url"}
    assert target.blockers[0].detail.startswith("remote origin has no push URL")


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
        "also deletes 1 ignored path inside it, including any Dashpot state, "
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
    project_session_store(worktree).write(
        HookRecord.model_validate(
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
            }
        )
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
    # The Branch keeps its own gate, and stays checked out while the Worktree
    # cannot go.
    assert kinds(local) == {"checked-out", "unintegrated"}
    assert preview.selectable == ()


# --- Agent Sessions here -----------------------------------------------------

SESSION = "01c7192b-2990-4f83-ad33-290ac22eb4d1"
THREAD = "01a05099-1563-79a3-8504-e30d50949ca6"
CLAUDE = ProcessIdentity(7777, 1, "claude", "Tue Aug 25 02:00:00 2026")
CODEX = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")
OPENCODE_SESSION = "ses_f059abdb5ffe6qbE35RQLOXLvj"
OPENCODE = ProcessIdentity(5151, 1, "opencode", "Tue Aug 25 03:00:00 2026")


# The way out of a Worktree each harness's session is given, verbatim.
CLAUDE_CODE_STEPS = (
    "run ExitWorktree with action: keep in that session if EnterWorktree "
    "brought it here, or cd its shell back to the checkout it started in if it "
    "came by cd (leaving any Agent Run here), or end that session"
)


def codex_steps(thread: str = THREAD) -> str:
    return (
        f"resume that session elsewhere with codex resume {thread} -C <worktree> "
        "once its client exits, running dashpot work relocate <worktree> in it "
        "first if it holds an Agent Run, or end that session's client (a "
        "daemon-hosted thread ends about 60 s after its last client leaves)"
    )


# An OpenCode v2 session can move, or be deleted, or lose its server.
OPENCODE_STEPS = (
    "move that session to another location in OpenCode, or delete that "
    f"session with opencode session delete {OPENCODE_SESSION}, or stop the "
    "OpenCode server it runs in, with opencode service stop or by quitting its "
    "--standalone client, which leaves every Agent Run on that server orphaned"
)


def occupied_worktree(
    tmp_path: Path,
    harness: str,
    session: str,
    process: ProcessIdentity | None,
    unobservable_reason: str | None = None,
) -> tuple[Path, tuple[Path, ...]]:
    """A linked Worktree whose hooks last placed one Agent Session there."""
    root = repo(tmp_path)
    branch(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    record: dict[str, object] = {
        "version": 2,
        "sessionId": session,
        "harness": harness,
        "state": "waiting",
        "cwd": str(worktree),
        "repositoryRoot": str(worktree),
        "branch": "feat",
        "event": "Stop",
        "lastActivityAt": "2026-09-30T03:40:00.000000Z",
    }
    if process is not None:
        record["sessionProcess"] = process.as_record()
    if unobservable_reason is not None:
        record["sessionProcessUnobservable"] = unobservable_reason
    project_session_store(worktree).write(HookRecord.model_validate(record))
    return worktree.resolve(), (root.resolve(), worktree.resolve())


def test_a_harness_without_its_own_way_out_is_given_the_general_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As a newly supported harness is until its entry is written.
    monkeypatch.delitem(SESSION_EXITS, "codex")
    worktree, worktrees = occupied_worktree(tmp_path, "codex", THREAD, CODEX)

    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({CODEX.pid: CODEX})
    )

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"Codex session {THREAD} is live here (last activity "
        "2026-09-30T03:40:00.000000Z). To free this Worktree, move that session "
        "out of this Worktree with its harness's own tool, or end that session.",
    )


def test_a_live_claude_code_session_here_names_its_worktree_tools(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "claude-code", SESSION, CLAUDE)

    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({CLAUDE.pid: CLAUDE})
    )

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"Claude Code session {SESSION} is live here (last activity "
        f"2026-09-30T03:40:00.000000Z). To free this Worktree, {CLAUDE_CODE_STEPS}.",
    )


def test_a_live_codex_session_here_names_its_resume_and_its_client(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "codex", THREAD, CODEX)

    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({CODEX.pid: CODEX})
    )

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"Codex session {THREAD} is live here (last activity "
        f"2026-09-30T03:40:00.000000Z). To free this Worktree, {codex_steps()}.",
    )


def test_a_live_opencode_session_here_names_what_serves_it(tmp_path: Path) -> None:
    worktree, worktrees = occupied_worktree(
        tmp_path, "opencode", OPENCODE_SESSION, OPENCODE
    )

    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({OPENCODE.pid: OPENCODE})
    )

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"OpenCode session {OPENCODE_SESSION} is live here (last activity "
        f"2026-09-30T03:40:00.000000Z). To free this Worktree, {OPENCODE_STEPS}.",
    )


def test_a_session_no_plugin_instance_observes_names_its_running_server(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(
        tmp_path,
        "opencode",
        OPENCODE_SESSION,
        OPENCODE,
        "opencode-no-live-instance",
    )

    # The server is observed and runs: nothing for a person to check with ps.
    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({OPENCODE.pid: OPENCODE})
    )

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"OpenCode session {OPENCODE_SESSION} may be live here: its "
        "liveness is unknown (last activity 2026-09-30T03:40:00.000000Z). Its "
        f"OpenCode server, pid {OPENCODE.pid}, still runs, but no Dashpot "
        "plugin instance has run in it since the session was last published. "
        f"To free this Worktree, {OPENCODE_STEPS}.",
    )


def test_a_session_no_plugin_instance_observes_frees_its_worktree_once_its_server_exits(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(
        tmp_path,
        "opencode",
        OPENCODE_SESSION,
        OPENCODE,
        "opencode-no-live-instance",
    )

    assert assess_worktree_occupancy(worktree, worktrees, absent()) == []


OPENCODE_KEY = "opencode-session-6d1f0c2a"


def bind_opencode_run(worktree: Path) -> None:
    """Record an OpenCode session's Agent Run on issue-10, served by OPENCODE."""
    WorkStore(worktree).start(
        ActiveWork(
            session_key=OPENCODE_KEY,
            harness="opencode",
            session_label=f"OpenCode session {OPENCODE_SESSION}",
            session_process=SessionProcess(
                pid=OPENCODE.pid, started_at=OPENCODE.started_at
            ),
            issue_id="I_10",
            issue_reference="issue-10",
            binding_provenance="explicit-reference",
            started_at="2026-09-30T03:35:00.000000Z",
            working_directory=str(worktree),
            branch="feat",
            session_id=OPENCODE_SESSION,
        )
    )


def test_a_live_opencode_run_is_stopped_inside_its_session(tmp_path: Path) -> None:
    worktree, worktrees = occupied_worktree(
        tmp_path, "opencode", OPENCODE_SESSION, OPENCODE
    )
    bind_opencode_run(worktree)

    blockers = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({OPENCODE.pid: OPENCODE})
    )

    assert [blocker.kind for blocker in blockers] == ["agent-session", "agent-run"]
    assert blockers[1] == CleanupBlocker(
        kind="agent-run",
        detail=f"OpenCode session {OPENCODE_SESSION} is working on issue-10 "
        "(session live)",
        command="dashpot work stop (inside that session)",
    )


def test_a_run_of_a_session_with_no_record_left_is_stopped_from_outside(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(
        tmp_path, "opencode", OPENCODE_SESSION, OPENCODE
    )
    bind_opencode_run(worktree)
    # As a deletion whose run was not ended leaves it: the hook record is
    # removed while the run and the server that served it remain.
    for record in session_directory(worktree).glob("*.json"):
        record.unlink()

    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, table_lookup({OPENCODE.pid: OPENCODE})
    )

    assert blocker == CleanupBlocker(
        kind="agent-run",
        detail=f"OpenCode session {OPENCODE_SESSION} is working on issue-10, "
        "but no hook record of that session is left while the OpenCode server "
        "that served it still runs: end the run",
        command=f"cd {worktree} && dashpot work stop --session {OPENCODE_KEY}",
    )


def test_a_run_of_a_deleted_opencode_session_is_orphaned_once_its_backend_exits(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(
        tmp_path, "opencode", OPENCODE_SESSION, OPENCODE
    )
    bind_opencode_run(worktree)
    for record in session_directory(worktree).glob("*.json"):
        record.unlink()

    (blocker,) = assess_worktree_occupancy(worktree, worktrees, absent())

    assert blocker.detail == (
        f"Orphaned Agent Run on issue-10 for OpenCode session {OPENCODE_SESSION}"
    )
    assert blocker.command == (
        f"cd {worktree} && dashpot work stop --session {OPENCODE_KEY}"
    )


def test_a_session_unobservable_from_a_sandbox_says_to_check_outside_it(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "claude-code", SESSION, CLAUDE)

    # Unknown is never evidence that the session ended, so it still blocks.
    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, unobservable("isolated-namespace")
    )

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"Claude Code session {SESSION} may be live here: its liveness "
        "is unknown (last activity 2026-09-30T03:40:00.000000Z). Dashpot cannot "
        f"see its Host Process, pid {CLAUDE.pid}, from inside this sandbox: "
        "check again from a shell outside it. If it is live, free this "
        f"Worktree: {CLAUDE_CODE_STEPS}.",
        command=f"env LC_ALL=C TZ=UTC ps -p {CLAUDE.pid} -o lstart=,args=",
    )


def test_a_session_whose_probe_failed_names_the_process_to_check(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "codex", THREAD, CODEX)

    (blocker,) = assess_worktree_occupancy(
        worktree, worktrees, unobservable("ps-unavailable")
    )

    # The start time tells the session's process from a later one at its pid.
    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"Codex session {THREAD} may be live here: its liveness is "
        "unknown (last activity 2026-09-30T03:40:00.000000Z). Dashpot could not "
        "observe its Host Process (ps-unavailable): check whether pid "
        f"{CODEX.pid}, started {CODEX.started_at} UTC, still runs. If it is live, "
        f"free this Worktree: {codex_steps()}.",
        command=f"env LC_ALL=C TZ=UTC ps -p {CODEX.pid} -o lstart=,args=",
    )


def test_a_session_with_no_recorded_host_process_cannot_be_verified(
    tmp_path: Path,
) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "codex", THREAD, None)

    (blocker,) = assess_worktree_occupancy(worktree, worktrees, absent())

    assert blocker == CleanupBlocker(
        kind="agent-session",
        detail=f"Codex session {THREAD} may be live here: its liveness is "
        "unknown, as its hook record names no Host Process (last activity "
        "2026-09-30T03:40:00.000000Z). If that session is still open, free "
        f"this Worktree: {codex_steps()}. If it has ended, resume it and end it "
        "again so that it publishes its end.",
    )


def test_finding_no_process_inside_leaves_a_live_session_blocking(
    tmp_path: Path,
) -> None:
    # The process check is positive only (ADR 0104): a session between tool
    # calls runs nothing in the Worktree and still occupies it.
    worktree, (root, _worktree) = occupied_worktree(
        tmp_path, "claude-code", SESSION, CLAUDE
    )

    preview = inspect_cleanup(
        WorktreeCleanupRequest(root, worktree),
        lookup=table_lookup({CLAUDE.pid: CLAUDE}),
        scan=scan_of(),
    )

    assert kinds(preview.targets[0]) == {"agent-session"}


def test_a_gone_session_here_does_not_block(tmp_path: Path) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "codex", THREAD, CODEX)

    assert assess_worktree_occupancy(worktree, worktrees, absent()) == []


def test_an_integrated_branch_under_a_blocked_worktree_stays_checked_out(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    (worktree / "scratch.txt").write_text("")

    preview = preview_worktree(root, worktree)

    tree, local = preview.targets
    assert kinds(tree) == {"dirty"}
    assert local.integration is not None
    assert local.integration.state == "integrated"
    (blocker,) = local.blockers
    assert blocker.kind == "checked-out"
    assert blocker.detail == f"checked out at {worktree}, whose removal is blocked"
    assert local.requires == tree.identity
    assert preview.selectable == ()


# --- Sub-agents -------------------------------------------------------------

PARENT = ProcessIdentity(7777, 1, "claude", "Tue Aug 25 02:00:00 2026")
PARENT_SESSION = "5fa2138c-418a-492c-9efb-c192fc0d6def"


def publish_subagent(
    store: Path,
    at: Path,
    event: str,
    agent: str,
    *,
    session: str = PARENT_SESSION,
    minute: int = 41,
    process: ProcessIdentity = PARENT,
) -> None:
    """Publish one sub-agent boundary as the Claude Code hook would.

    Its ``cwd`` is the parent's location, whatever directory the sub-agent
    works in, as measured on Claude Code 2.1.285; the store derives the live
    set from the event.
    """
    HookRecordStore(store).write(
        HookRecord.model_validate(
            {
                "version": 2,
                "sessionId": session,
                "harness": "claude-code",
                "state": "running" if event == "SubagentStart" else "waiting",
                "cwd": str(at),
                "repositoryRoot": str(at),
                "branch": "main",
                "event": event,
                "agentId": agent,
                "lastActivityAt": f"2026-08-30T03:{minute:02d}:00.000000Z",
                "sessionProcess": process.as_record(),
            }
        )
    )


def sub_agent_worktrees(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A Repository with two clean linked Worktrees, on integrated Branches."""
    root = repo(tmp_path)
    for name in ("feat", "other"):
        branch(root, name)
        integrate(root, name)
    target = tmp_path / "wt"
    sibling = tmp_path / "sibling"
    git(root, "worktree", "add", "-q", str(target), "feat")
    git(root, "worktree", "add", "-q", str(sibling), "other")
    return root, target, sibling


def test_finding_no_process_inside_leaves_a_sub_agent_blocking(
    tmp_path: Path,
) -> None:
    # A sub-agent between commands runs nothing in any Worktree (ADR 0104).
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")

    preview = inspect_cleanup(
        WorktreeCleanupRequest(root, target),
        lookup=table_lookup({PARENT.pid: PARENT}),
        scan=scan_of(),
    )

    assert kinds(preview.targets[0]) == {"sub-agent"}


def test_a_live_sub_agent_blocks_every_worktree_it_could_be_working_in(
    tmp_path: Path,
) -> None:
    root, target, sibling = sub_agent_worktrees(tmp_path)
    # The parent is at the main Worktree; one sub-agent works in the target
    # and one in the sibling, which the hooks cannot tell apart.
    publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")
    publish_subagent(session_directory(root), root, "SubagentStart", "a3932", minute=42)
    lookup = table_lookup({PARENT.pid: PARENT})

    for path in (target, sibling):
        preview = preview_worktree(root, path, lookup=lookup)
        tree, _local = preview.targets
        assert tree.available is False
        (blocker,) = tree.blockers
        assert blocker.kind == "sub-agent"
        assert blocker.detail == (
            f"Claude Code session {PARENT_SESSION} at {root} has 2 sub-agents "
            "listed as working (a3932, a686b12; session live). Dashpot cannot "
            "tell which Worktree a sub-agent works in, so one may be "
            "working here: wait for it to finish. Dashpot lists a sub-agent "
            "until Claude Code reports that it stopped, which one that was "
            "stopped or interrupted may never do, so if none is still working, "
            "end that session."
        )
        assert blocker.session_id == PARENT_SESSION
        assert blocker.harness == "claude-code"
        assert blocker.agents == ("a3932", "a686b12")
        # Only the sub-agents hold it, so a person's acknowledgement could
        # remove it, and the scope that removal would rest on is stated
        # beside the exact flag value (ADR 0112).
        text = describe_cleanup_preview(preview)
        assert SUB_AGENT_SCOPE in "\n".join(text)
        assert f"          --despite-subagents {PARENT_SESSION}:a3932,a686b12" in text


def test_a_live_codex_sub_agent_blocks_like_a_claude_code_one(
    tmp_path: Path,
) -> None:
    # Codex publishes its delegated threads' boundaries too, through the
    # same hook seam (ADR 0067), so ADR 0066's blocker covers them.
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    codex = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")
    thread = "01a05099-1563-79a3-8504-e30d50949ca6"
    for event in ("UserPromptSubmit", "SubagentStart", "Stop"):
        publish_hook_event(
            {
                "session_id": thread,
                "cwd": str(root),
                "hook_event_name": event,
                **({"agent_id": "child-thread"} if event == "SubagentStart" else {}),
            },
            directory=session_directory(root),
            process=codex,
            harness="codex",
        )

    tree, _local = preview_worktree(
        root, target, lookup=table_lookup({codex.pid: codex})
    ).targets

    (blocker,) = tree.blockers
    assert blocker.kind == "sub-agent"
    assert blocker.detail == (
        f"Codex session {thread} at {root.resolve()} has 1 sub-agent listed "
        "as working (child-thread; session live). Dashpot cannot tell which "
        "Worktree a sub-agent works in, so one may be working here: wait "
        "for it to finish. Dashpot lists a sub-agent until Codex reports that "
        "it stopped, which one that was stopped or interrupted may never do, "
        "so if none is still working, end that session's client (a "
        "daemon-hosted thread ends about 60 s after its last client leaves)."
    )


def test_a_stopped_sub_agent_no_longer_blocks(tmp_path: Path) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    store = session_directory(root)
    publish_subagent(store, root, "SubagentStart", "a686b12")
    publish_subagent(store, root, "SubagentStop", "a686b12", minute=42)

    preview = preview_worktree(root, target, lookup=table_lookup({PARENT.pid: PARENT}))

    assert preview.targets[0].available is True


def test_a_sub_agent_still_blocks_after_its_parent_moves_to_another_worktree(
    tmp_path: Path,
) -> None:
    root, target, sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")
    # The parent then enters the sibling, whose store has no previous record
    # of the session and so no sub-agents to carry.
    project_session_store(sibling).write(
        HookRecord.model_validate(
            {
                "version": 2,
                "sessionId": PARENT_SESSION,
                "harness": "claude-code",
                "state": "running",
                "cwd": str(sibling),
                "repositoryRoot": str(sibling),
                "branch": "other",
                "event": "UserPromptSubmit",
                "lastActivityAt": "2026-08-30T03:45:00.000000Z",
                "sessionProcess": PARENT.as_record(),
            }
        )
    )

    preview = preview_worktree(root, target, lookup=table_lookup({PARENT.pid: PARENT}))

    (blocker,) = preview.targets[0].blockers
    assert blocker.kind == "sub-agent"
    assert blocker.detail.startswith(
        f"Claude Code session {PARENT_SESSION} at {sibling} has 1 sub-agent "
        "listed as working (a686b12; session live)."
    )


def test_a_record_left_by_a_gone_process_holds_no_sub_agent(
    tmp_path: Path,
) -> None:
    root, target, sibling = sub_agent_worktrees(tmp_path)
    # A process that has since exited dispatched a sub-agent at the main
    # Worktree; the session now runs under the live parent at the sibling.
    exited = ProcessIdentity(6666, 1, "claude", "Tue Aug 25 01:00:00 2026")
    publish_subagent(
        session_directory(root), root, "SubagentStart", "a686b12", process=exited
    )
    publish_subagent(
        session_directory(sibling), sibling, "SubagentStop", "a3932", minute=45
    )

    preview = preview_worktree(root, target, lookup=table_lookup({PARENT.pid: PARENT}))

    assert preview.targets[0].available is True


def test_a_parent_session_that_is_gone_leaves_no_sub_agent_blocker(
    tmp_path: Path,
) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")

    preview = preview_worktree(root, target, lookup=absent())

    assert preview.targets[0].available is True


def test_a_parent_of_unknown_liveness_still_blocks(tmp_path: Path) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")

    preview = preview_worktree(root, target, lookup=unobservable("ps is unavailable"))

    (blocker,) = preview.targets[0].blockers
    assert blocker.kind == "sub-agent"
    assert "session unknown" in blocker.detail


def test_a_session_outside_the_repository_does_not_block(tmp_path: Path) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    publish_subagent(state_directory(), elsewhere, "SubagentStart", "a686b12")

    preview = preview_worktree(root, target, lookup=table_lookup({PARENT.pid: PARENT}))

    assert preview.targets[0].available is True
    # The gap #357 accepted is stated with the Worktree the preview offers.
    lines = describe_cleanup_preview(preview)
    branch_line = next(line for line in lines if line.startswith("  [ ] Local Branch"))
    assert lines.index(f"      {SUB_AGENT_SCOPE}") == lines.index(branch_line) - 1


def test_a_session_here_with_sub_agents_is_one_occupant(tmp_path: Path) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(target), target, "SubagentStart", "a686b12")

    preview = preview_worktree(root, target, lookup=table_lookup({PARENT.pid: PARENT}))

    assert kinds(preview.targets[0]) == {"agent-session"}


def test_a_sub_agent_started_after_the_preview_refuses_the_removal(
    tmp_path: Path,
) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    lookup = table_lookup({PARENT.pid: PARENT})
    request = WorktreeCleanupRequest(root, target)
    preview = inspect_cleanup(request, lookup=lookup)
    tree, _local = preview.targets
    assert tree.available is True
    store = session_directory(root)
    publish_subagent(store, root, "SubagentStart", "a686b12")

    refused = perform_cleanup(confirm(request, preview, tree.identity), lookup=lookup)

    assert refused.performed is False
    assert refused.refusals == (CHANGED_SINCE_PREVIEW,)
    assert kinds(refused.preview.targets[0]) == {"sub-agent"}
    assert target.exists()
    # Confirming the revised preview is refused too, until the sub-agent stops.
    blocked = perform_cleanup(
        confirm(request, refused.preview, tree.identity), lookup=lookup
    )
    assert blocked.performed is False
    assert blocked.refusals
    assert target.exists()

    publish_subagent(store, root, "SubagentStop", "a686b12", minute=42)
    fresh = inspect_cleanup(request, lookup=lookup)
    removed = perform_cleanup(confirm(request, fresh, tree.identity), lookup=lookup)

    assert removed.succeeded is True
    assert not target.exists()


def pushed_worktree(tmp_path: Path) -> tuple[Path, Path, str]:
    """An integrated ``feat`` in a linked Worktree, also at ``origin`` and ``upstream``."""
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    track(root, "feat", tip)
    git(root, "remote", "add", "upstream", str(tmp_path / "upstream.git"))
    track(root, "feat", tip, remote="upstream")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    return root, worktree, tip


def test_a_worktree_offers_its_branch_at_the_push_remote_only(tmp_path: Path) -> None:
    root, worktree, tip = pushed_worktree(tmp_path)

    preview = preview_worktree(root, worktree)

    tree, local, pushed = preview.targets
    # Nothing configures where feat is pushed, so Git's answer is origin; the
    # same Branch at upstream stays the Branches pane's to delete.
    assert pushed.identity == "remote:origin:refs/heads/feat"
    assert pushed.label == "Branch at origin"
    assert pushed.expected == tip
    assert pushed.requires == tree.identity
    assert pushed.available is True
    assert default_choices(preview) == (local.identity, pushed.identity)
    # A held local Branch never lets the remote one start selected alone.
    held = local.model_copy(
        update={"blockers": (CleanupBlocker(kind="protected", detail="held"),)}
    )
    assert (
        default_choices(preview.model_copy(update={"targets": (tree, held, pushed)}))
        == ()
    )


@pytest.mark.parametrize(
    ("config", "remote"),
    [
        ({"branch.feat.pushRemote": "upstream"}, "upstream"),
        ({"remote.pushDefault": "upstream"}, "upstream"),
        ({"branch.feat.remote": "upstream"}, "upstream"),
        (
            {"branch.feat.pushRemote": "origin", "remote.pushDefault": "upstream"},
            "origin",
        ),
        ({"branch.feat.remote": "."}, None),
        ({"remote.pushDefault": "gone"}, None),
    ],
)
def test_the_push_remote_follows_gits_order(
    tmp_path: Path, config: dict[str, str], remote: str | None
) -> None:
    root, worktree, _tip = pushed_worktree(tmp_path)
    for key, value in config.items():
        git(root, "config", key, value)

    preview = preview_worktree(root, worktree)

    offered = [
        target.remote for target in preview.targets if target.kind == "remote-branch"
    ]
    assert offered == ([remote] if remote else [])


def test_a_branch_never_fetched_at_its_push_remote_offers_no_remote_target(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")

    preview = preview_worktree(root, worktree)

    assert [target.kind for target in preview.targets] == ["worktree", "local-branch"]


def test_a_remote_branch_off_the_local_tip_is_offered_but_not_by_default(
    tmp_path: Path,
) -> None:
    root, worktree, tip = pushed_worktree(tmp_path)
    # Someone moved origin's feat to an older, still integrated commit.
    track(root, "feat", f"{tip}~1")

    preview = preview_worktree(root, worktree)

    _tree, local, pushed = preview.targets
    assert pushed.available is True
    assert pushed.expected != local.expected
    assert default_choices(preview) == (local.identity,)
    # A Branch preview is a general editor: nothing starts selected there.
    assert default_choices(preview_branch(root, "feat")) == ()


def test_a_blocked_worktree_holds_its_remote_branch_too(tmp_path: Path) -> None:
    root, worktree, _tip = pushed_worktree(tmp_path)
    (worktree / "scratch.txt").write_text("")

    preview = preview_worktree(root, worktree)

    tree, local, pushed = preview.targets
    assert kinds(tree) == {"dirty"}
    assert kinds(local) == kinds(pushed) == {"checked-out"}
    # The Branch at the remote is not itself checked out anywhere.
    assert pushed.blockers[0].detail == (
        f"its local Branch is checked out at {worktree}, whose removal is blocked"
    )
    assert preview.selectable == ()
    assert default_choices(preview) == ()


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
    assert kinds(main.targets[1]) == {"integration-branch", "checked-out"}


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


@pytest.mark.parametrize(
    ("origin", "origin_head", "second_default", "integration_ref"),
    [
        (True, None, False, "refs/remotes/origin/main"),
        (False, "refs/heads/main", True, "refs/heads/main"),
        (False, None, False, "refs/heads/main"),
        (False, None, True, None),
    ],
    ids=["origin-head", "origin-head-at-local", "local-default", "none"],
)
def test_preview_and_removability_agree_on_the_integration_branch(
    tmp_path: Path,
    origin: bool,
    origin_head: str | None,
    second_default: bool,
    integration_ref: str | None,
) -> None:
    root = repo(tmp_path, origin=origin)
    branch(root, "feat")
    if origin_head is not None:
        git(root, "symbolic-ref", "refs/remotes/origin/HEAD", origin_head)
    if second_default:
        git(root, "branch", "master", "main")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")

    _tree, local = preview_worktree(root, worktree).targets
    report = check_worktree(root, worktree)

    assert local.integration is not None
    assert local.integration.integration_ref == integration_ref
    (gate,) = local.blockers
    (unmerged,) = [item for item in report.obstacles if item.kind == "unmerged"]
    if integration_ref is None:
        assert gate.kind == "unknown-integration"
        assert gate.detail == NO_INTEGRATION_BRANCH
        assert unmerged.detail.endswith(NO_INTEGRATION_BRANCH)
    else:
        assert gate.kind == "unintegrated"
        assert gate.detail == (
            f"1 commit not reachable from {short_ref(integration_ref)}"
        )
        assert unmerged.detail == gate.detail


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
        "uncheckedProcesses",
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
    assert lines[1] == f"Anchor          {root.resolve()}"
    assert lines[2] == "Targets"
    assert lines[3] == f"  [ ] Local Branch refs/heads/feat @ {tip[:7]} — unavailable"
    assert lines[4] == "      ↑ commits are not reachable from the Integration Branch"
    assert lines[5] == (
        "      blocked: unintegrated: 1 commit not reachable from origin/main"
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


def test_only_the_confirmed_cleanup_runs_through_a_dashboard_exit(
    tmp_path: Path,
) -> None:
    # On a thread whose registry an exit has closed, the preview's adapter is
    # refused like any observation while the removal's still runs.
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    request = BranchCleanupRequest(root, "feat")
    adapter = GitCleanupAdapter(5)
    running = RunningCommands()
    running.interrupt()

    def preview_then_perform() -> CleanupReport:
        running.adopt()
        with pytest.raises(GitError, match="interrupted at shutdown"):
            adapter.inspect(request, protected=())
        finishing = Git(root, 5, non_interactive_runner(interruptible=False))
        preview = inspect_cleanup(request, git=finishing)
        (local,) = preview.targets
        return adapter.perform(confirm(request, preview, local.identity), protected=())

    report = copy_context().run(preview_then_perform)

    assert report.succeeded is True
    assert "refs/heads/feat" not in git(root, "for-each-ref")


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


def test_state_ignoring_itself_after_the_preview_leaves_the_removal_confirmed(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    # State an earlier Dashpot wrote before its directory ignored itself,
    # which no store can produce now, so it is written directly.
    state = worktree / ".dashpot" / "state" / "work"
    state.mkdir(parents=True)
    (state / ".codex-4242.lock").write_text("")
    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)
    (tree, _local) = preview.targets

    ensure_state_directory(worktree)
    report = perform_cleanup(
        confirm(request, preview, tree.identity, delete_ignored=True)
    )

    assert preview.ignored == (".dashpot/", ".venv/")
    assert report.changed is False
    assert report.succeeded is True
    assert not worktree.exists()


def test_state_created_after_the_preview_refuses_the_removal(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)
    (tree, _local) = preview.targets

    # The acknowledgement covered the ignored content the preview listed, not
    # state a session wrote since.
    ensure_state_directory(worktree)
    report = perform_cleanup(
        confirm(request, preview, tree.identity, delete_ignored=True)
    )

    assert report.changed is True
    assert report.refusals == (CHANGED_SINCE_PREVIEW,)
    assert ".dashpot/" in report.preview.ignored
    assert worktree.exists()


def test_state_ignoring_itself_without_a_rule_unblocks_the_worktree(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path, ignore_state=False)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    # State an earlier Dashpot wrote in a Project with no rule for it.
    state = worktree / ".dashpot" / "state" / "work"
    state.mkdir(parents=True)
    (state / ".codex-4242.lock").write_text("")
    request = WorktreeCleanupRequest(root, worktree)
    stale = inspect_cleanup(request)
    (stale_tree, _local) = stale.targets

    ensure_state_directory(worktree)
    fresh = inspect_cleanup(request)
    (tree, _local) = fresh.targets
    # The person confirmed a preview that found the Worktree dirty; the one
    # that offers its removal is a different preview, so it is refused.
    refused = perform_cleanup(
        confirm(request, stale, stale_tree.identity, delete_ignored=True)
    )
    assert worktree.exists()
    removed = perform_cleanup(
        confirm(request, fresh, tree.identity, delete_ignored=True)
    )

    assert kinds(stale_tree) == {"dirty"}
    assert tree.available is True
    assert fresh.ignored == (".dashpot/", ".venv/")
    assert refused.changed is True
    assert refused.refusals == (CHANGED_SINCE_PREVIEW,)
    assert removed.succeeded is True
    assert not worktree.exists()


def ignore_claude(root: Path) -> None:
    """Ignore ``.claude/`` in every Worktree of the Repository, as Projects do."""
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    with (common / "info" / "exclude").open("a") as rules:
        rules.write(".claude/\n")


def nest_worktree(root: Path, parent: Path, name: str) -> Path:
    """A dirty Worktree registered under ``parent``'s ``.claude/worktrees/``.

    Claude Code's ``EnterWorktree`` creates its Worktrees there, inside the
    session's checkout.
    """
    nested = parent / ".claude" / "worktrees" / name
    git(root, "worktree", "add", "-q", "-b", name, str(nested))
    (nested / "uncommitted.txt").write_text("work no commit holds\n")
    return nested.resolve()


def test_a_worktree_holding_another_is_blocked_until_that_one_goes(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    ignore_claude(root)
    nested = nest_worktree(root, worktree, "inner")
    request = WorktreeCleanupRequest(root, worktree)

    preview = inspect_cleanup(request)
    tree, local = preview.targets
    report = perform_cleanup(
        confirm(request, preview, tree.identity, local.identity, delete_ignored=True)
    )
    checked = check_worktree(root, worktree)

    # The Worktree's own status sees the nested one only as an ignored path.
    assert preview.ignored == (".claude/", ".venv/")
    assert tree.blockers == (
        CleanupBlocker(
            kind="nested-worktree",
            detail=f"the Worktree {nested} is inside this one, and removing this "
            f"Worktree would delete it without checking it: remove it first, or "
            f"move it out with git worktree move",
            command=f"dashpot worktree remove {nested}",
        ),
    )
    assert kinds(local) == {"checked-out"}
    assert report.performed is False
    assert report.refusals[0].startswith("Worktree is unavailable: the Worktree ")
    assert (nested / "uncommitted.txt").exists()
    assert checked.removable is False
    assert checked.obstacles == tree.blockers
    # The published shape carries the kind, the Worktree inside, and its command.
    (published,) = cleanup_preview_document(preview)["targets"][0]["blockers"]
    assert published == {
        "kind": "nested-worktree",
        "detail": tree.blockers[0].detail,
        "command": f"dashpot worktree remove {nested}",
        "sessionId": None,
        "harness": None,
        "agents": [],
    }
    assert removability_document(checked)["obstacles"] == [published]
    lines = describe_cleanup_preview(preview)
    assert f"      blocked: nested-worktree: {tree.blockers[0].detail}" in lines
    assert f"          run: dashpot worktree remove {nested}" in lines
    assert f"  - nested-worktree: {tree.blockers[0].detail}" in describe_removability(
        checked
    )


def test_a_worktree_nested_after_the_preview_refuses_the_removal(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    ignore_claude(root)
    # An ignored directory the preview already lists, so the ignored inventory
    # is the same before and after the nested Worktree appears in it.
    (worktree / ".claude").mkdir()
    (worktree / ".claude" / "settings.local.json").write_text("{}\n")
    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)
    (tree, _local) = preview.targets

    nested = nest_worktree(root, worktree, "inner")
    report = perform_cleanup(
        confirm(request, preview, tree.identity, delete_ignored=True)
    )

    assert tree.available is True
    assert preview.ignored == (".claude/", ".venv/")
    assert report.changed is True
    assert report.refusals == (CHANGED_SINCE_PREVIEW,)
    assert report.preview.ignored == preview.ignored
    assert kinds(report.preview.targets[0]) == {"nested-worktree"}
    assert (nested / "uncommitted.txt").exists()


def test_a_stale_record_inside_a_worktree_blocks_until_it_is_pruned(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    ignore_claude(root)
    nested = nest_worktree(root, worktree, "inner")
    # Its directory deleted by hand, its record left behind as prunable.
    shutil.rmtree(nested)
    request = WorktreeCleanupRequest(root, worktree)

    stale = inspect_cleanup(request)
    git(root, "worktree", "prune")
    pruned = inspect_cleanup(request)

    assert stale.targets[0].blockers == (
        CleanupBlocker(
            kind="nested-worktree",
            detail=f"a stale record of the Worktree {nested}, whose directory is "
            f"gone, is inside this one: prune it first",
            command="git worktree prune",
        ),
    )
    assert pruned.targets[0].available is True


def test_the_main_worktree_lists_no_worktree_inside_it(tmp_path: Path) -> None:
    root = repo(tmp_path)
    ignore_claude(root)
    nest_worktree(root, root, "inner")

    main = preview_worktree(root, root)

    assert kinds(main.targets[0]) == {"main-worktree"}


@pytest.mark.parametrize("setting", ["no", "all"])
def test_the_ignored_inventory_ignores_the_untracked_files_setting(
    tmp_path: Path, setting: str
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    (worktree / ".venv" / "lib").mkdir()
    (worktree / ".venv" / "lib" / "site.py").write_text("")
    git(root, "config", "status.showUntrackedFiles", setting)
    request = WorktreeCleanupRequest(root, worktree)

    preview = inspect_cleanup(request)
    (tree, _local) = preview.targets
    unacknowledged = perform_cleanup(confirm(request, preview, tree.identity))

    # ``no`` would list nothing and drop the acknowledgement; ``all`` would
    # list every file inside, so a file written there would change the preview.
    assert preview.ignored == (".venv/",)
    assert tree.available is True
    assert unacknowledged.performed is False
    assert unacknowledged.refusals == (
        "removing the Worktree deletes 1 ignored path inside it, which must be "
        "acknowledged",
    )
    assert worktree.exists()


def test_an_ignored_inventory_git_refuses_blocks_the_removal(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)

    def refusing(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if "--ignored=traditional" in args:
            return CommandResult(list(args), 128, "", "fatal: index file corrupt\n")
        return run_command(args, cwd, timeout)

    preview = inspect_cleanup(request, git=Git(root, 5, refusing))
    tree, local = preview.targets

    # Failing to list is not finding nothing.
    assert preview.ignored == ()
    assert tree.blockers == (
        CleanupBlocker(
            kind="ignored-content",
            detail="cannot list the ignored content removing this Worktree would "
            "delete: fatal: index file corrupt",
            command=f"git -C {worktree.resolve()} status --ignored "
            "--untracked-files=normal",
        ),
    )
    assert kinds(local) == {"checked-out"}


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
        "Local Branch is unavailable: 1 commit not reachable from origin/main",
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
        "removing the Worktree deletes 1 ignored path inside it, which must be "
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


def test_the_delete_push_carries_the_lease_and_nothing_touches_the_tracking_ref(
    tmp_path: Path,
) -> None:
    root, _bare, tip = served_feature(tmp_path)
    request = BranchCleanupRequest(root, "feat")
    mutations: list[tuple[str, ...]] = []

    def recording(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        # Every Git command that could write; ``worktree list``, ``config
        # --get-all``, and the rest are reads and stay out of the record.
        if (
            args[1] in {"push", "update-ref", "branch"}
            or (args[1] == "config" and "--get-all" not in args)
            or (args[1] == "worktree" and args[2] != "list")
        ):
            mutations.append(tuple(args[1:]))
        return run_command(args, cwd, timeout)

    git_ = Git(root, 5, recording)
    preview = inspect_cleanup(request, git=git_)
    mutations.clear()
    report = perform_cleanup(
        confirm(
            request, preview, "remote:origin:refs/heads/feat", "local:refs/heads/feat"
        ),
        git=git_,
    )

    assert report.succeeded is True
    assert mutations == [
        (
            "push",
            f"--force-with-lease=refs/heads/feat:{tip}",
            "origin",
            ":refs/heads/feat",
        ),
        ("update-ref", "-d", "refs/heads/feat", tip),
        ("config", "--remove-section", "branch.feat"),
    ]


def test_a_remote_that_moved_refuses_the_lease_and_halts_the_local(
    tmp_path: Path,
) -> None:
    root, bare, tip = served_feature(tmp_path)
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(bare), str(other))
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
        f"last fetch; press f (or git fetch --prune origin), then confirm against "
        f"the revised preview"
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
        "feat at origin was already gone; the stale refs/remotes/origin/feat is "
        "pruned by the next Remote Fetch: press f, or git fetch --prune origin"
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
            raise CommandError("timed out after 5.0s")
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
        "refs/remotes/origin/feat is pruned by the next Remote Fetch: press f, or "
        "git fetch --prune origin"
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


def test_removing_a_worktree_finishes_its_branch_at_the_remote_first(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    tip = branch(root, "feat")
    integrate(root, "feat")
    bare = serve(tmp_path, root, "feat")
    git(root, "fetch", "-q", "origin")
    worktree = linked(tmp_path, root, "feat")
    request = WorktreeCleanupRequest(root, worktree)
    preview = inspect_cleanup(request)

    # The defaults name only the optional targets; the Worktree is the subject.
    tree = preview.targets[0].identity
    report = perform_cleanup(
        confirm(request, preview, tree, *default_choices(preview), delete_ignored=True)
    )

    assert report.succeeded is True
    assert [result.kind for result in report.results] == [
        "remote-branch",
        "worktree",
        "local-branch",
    ]
    assert git(bare, "for-each-ref", "refs/heads/feat") == ""
    assert (
        git(root, "for-each-ref", "refs/remotes/origin/feat", "refs/heads/feat") == ""
    )
    assert not worktree.exists()
    assert git(root, "rev-parse", "main") == tip


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
            raise CommandError("timed out after 5.0s")
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
    assert lines[4] == f"     {SUB_AGENT_SCOPE}"
    assert lines[5] == "  2. Local Branch refs/heads/feat"


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
    assert lines[1] == f"Anchor          {root.resolve()}"
    assert lines[2] == "Results"
    assert lines[3] == f"  deleted        Local Branch refs/heads/feat @ {tip[:7]}"
    assert lines[4] == f"      deleted refs/heads/feat at {tip[:7]}"
    assert lines[5] == f"      recover: git branch feat {tip}"

    changed = perform_cleanup(confirm(request, preview, "local:refs/heads/feat"))
    lines = describe_cleanup_report(changed)
    assert lines[2] == f"Changed         {CHANGED_SINCE_PREVIEW}"
    assert lines[3].startswith("Refused         no Branch named feat at ")


def test_a_reason_counts_in_agreement_and_names_refs_as_a_person_reads_them():
    assert counted(1, "commit") == "1 commit"
    assert counted(0, "commit") == "0 commits"
    assert counted(3, "ignored path") == "3 ignored paths"
    assert short_ref("refs/heads/feat") == "feat"
    assert short_ref("refs/remotes/origin/feat") == "origin/feat"
