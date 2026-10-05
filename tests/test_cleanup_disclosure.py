"""What a Cleanup preview discloses, and the one verdict ``worktree check`` shares.

A Branch is in use wherever Git says it is, rebases and bisects included; a
confirmation compares every disclosed fact but the named exclusions; every
command it shows is quoted for a shell; one predicate tells an Orphaned
Agent Run; and ``worktree check`` assesses a Worktree by the preview's own
sequence and protection.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from dashpot.core.shell import in_directory, shell_command
from dashpot.repository.cleanup import (
    CHANGED_SINCE_PREVIEW,
    BranchCleanupRequest,
    CleanupBlocker,
    CleanupPreview,
    IntegrationFact,
    WorktreeCleanupRequest,
    inspect_cleanup,
    perform_cleanup,
    protected_checkouts,
)
from dashpot.repository.cleanup.adapter import GitCleanupAdapter
from dashpot.repository.cleanup.obstacles import assess_worktree_occupancy
from dashpot.repository.cleanup.override import lifted
from dashpot.repository.cleanup.selection import retained_choices
from dashpot.repository.cleanup.targets import disclosed_facts, fingerprint
from dashpot.repository.worktrees.removability import (
    check_worktree,
    describe_removability,
)
from dashpot.sessions.liveness import LivenessObservation, SessionLiveness
from dashpot.sessions.orphaned_runs import orphaned_process
from dashpot.sessions.work_store import (
    ActiveWork,
    RelocationIntent,
    SessionProcess,
    WorkStore,
)
from factories import git
from helpers import absent
from test_cleanup import (
    CODEX,
    THREAD,
    branch,
    by_identity,
    confirm,
    ignore_claude,
    integrate,
    kinds,
    linked,
    nest_worktree,
    occupied_worktree,
    preview_branch,
    preview_worktree,
    repo,
)
from test_subagent_override import BOTH, perform, removing, shown, two_subagents

LOCAL_FEAT = "local:refs/heads/feat"


def run_shell(command: str, cwd: Path) -> None:
    """Run a displayed command as a person pasting it into a shell would."""
    subprocess.run(["bash", "-c", command], cwd=cwd, check=True, capture_output=True)


# --- A Branch in use ---------------------------------------------------------


def rebasing(root: Path, worktree: Path) -> None:
    """Stop a rebase of the Branch checked out at ``worktree`` partway."""
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    rebasing_here(worktree)
    # Git lists a Worktree mid-rebase as detached, naming no Branch.
    assert "detached" in git(root, "worktree", "list", "--porcelain")


def rebasing_here(worktree: Path) -> None:
    """Stop a rebase of the Branch checked out at ``worktree`` partway."""
    subprocess.run(
        ["git", "rebase", "--exec", "false", "HEAD~1"],
        cwd=worktree,
        capture_output=True,
        check=False,
    )


def test_a_branch_being_rebased_in_another_worktree_is_in_use(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = tmp_path / "wt"
    rebasing(root, worktree)
    # An administrative directory left without its ``gitdir`` names no
    # Worktree, and is passed over; it sorts before the one rebasing.
    (root / ".git" / "worktrees" / "0-abandoned").mkdir()

    local = by_identity(preview_branch(root, "feat"))[LOCAL_FEAT]

    assert local.available is False
    assert local.blockers == (
        CleanupBlocker(
            kind="checked-out",
            detail=f"being rebased at {worktree.resolve()}; finish or abort that "
            "rebase first",
            command=f"git -C {worktree.resolve()} status",
        ),
    )
    # Git refuses the deletion for the same reason.
    refused = subprocess.run(
        ["git", "branch", "-d", "feat"], cwd=root, capture_output=True, text=True
    )
    assert refused.returncode != 0


def test_a_branch_being_rebased_in_the_main_worktree_is_in_use(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    git(root, "checkout", "-q", "feat")
    subprocess.run(
        ["git", "rebase", "--exec", "false", "HEAD~1"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    local = by_identity(preview_branch(root, "feat"))[LOCAL_FEAT]

    assert [(one.kind, one.detail) for one in local.blockers] == [
        (
            "checked-out",
            f"being rebased at {root.resolve()}; finish or abort that rebase first",
        )
    ]


def test_a_branch_being_bisected_in_another_worktree_is_in_use(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat", commits=3)
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    # A bisect between the Branch and main checks a commit out detached.
    git(worktree, "bisect", "start", "feat", "main")
    assert "detached" in git(root, "worktree", "list", "--porcelain")

    local = by_identity(preview_branch(root, "feat"))[LOCAL_FEAT]

    (checked_out,) = [one for one in local.blockers if one.kind == "checked-out"]
    assert checked_out == CleanupBlocker(
        kind="checked-out",
        detail=f"being bisected at {worktree.resolve()}; end that bisect first",
        command=f"git -C {worktree.resolve()} bisect reset",
    )


def test_a_branch_rebased_by_a_stack_in_another_worktree_is_in_use(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "low")
    git(root, "checkout", "-q", "-b", "top", "low")
    git(root, "commit", "-q", "--allow-empty", "-m", "top")
    git(root, "checkout", "-q", "main")
    git(root, "commit", "-q", "--allow-empty", "-m", "main moves on")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "top")
    # Stop at the first commit, with ``low`` still to be moved.
    subprocess.run(
        ["git", "rebase", "-i", "--update-refs", "main"],
        cwd=worktree,
        env={**os.environ, "GIT_SEQUENCE_EDITOR": "sed -i 1s/^pick/edit/"},
        capture_output=True,
        check=False,
    )

    local = by_identity(preview_branch(root, "low"))["local:refs/heads/low"]

    assert (
        "checked-out",
        f"being rebased at {worktree.resolve()}; finish or abort that rebase first",
    ) in [(one.kind, one.detail) for one in local.blockers]


def test_a_sub_agent_override_never_lifts_a_branch_in_use_elsewhere(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    second = tmp_path / "second"
    git(root, "worktree", "add", "-q", "-f", str(second), "feat")
    rebasing_here(second)
    preview = shown(root, target)
    tree = next(one for one in preview.targets if one.kind == "worktree")
    held = next(one for one in preview.targets if one.kind == "local-branch")

    report = perform(removing(preview, root, target, BOTH))

    assert lifted(preview, BOTH) == {tree.identity}
    assert held.identity not in lifted(preview, BOTH)
    assert report.performed is False
    assert any("being rebased at" in refusal for refusal in report.refusals)
    assert target.exists()
    git(root, "rev-parse", "--verify", "refs/heads/feat")


def test_a_branch_checked_out_in_a_second_worktree_stays_after_removing_one(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    second = tmp_path / "second"
    git(root, "worktree", "add", "-q", "-f", str(second), "feat")

    tree, local = preview_worktree(root, worktree).targets[:2]

    assert tree.available is True
    assert local.identity == LOCAL_FEAT
    assert local.blockers == (
        CleanupBlocker(
            kind="checked-out",
            detail=f"checked out at {second.resolve()}; remove that Worktree first",
        ),
    )


def test_a_branch_in_use_only_by_the_worktree_removed_is_offered(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")

    local = by_identity(preview_worktree(root, worktree))[LOCAL_FEAT]

    assert local.available is True


# --- What a confirmation compares -------------------------------------------


def integrated_preview(tmp_path: Path) -> CleanupPreview:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    return preview_branch(root, "feat")


def with_target(preview: CleanupPreview, **changes: object) -> CleanupPreview:
    (target, *rest) = preview.targets
    revised = preview.model_copy(
        update={"targets": (target.model_copy(update=changes), *rest)}
    )
    return revised.model_copy(update={"fingerprint": fingerprint(revised)})


def test_the_fingerprint_counts_every_disclosed_fact(tmp_path: Path) -> None:
    preview = integrated_preview(tmp_path)
    target = preview.targets[0]
    assert fingerprint(preview) == preview.fingerprint

    content = with_target(
        preview,
        integration=IntegrationFact(
            integration_ref="refs/remotes/origin/main",
            unintegrated_commits=1,
            content_integrated=True,
        ),
    )
    worded = with_target(preview, consequences=("deletes it differently",))
    labelled = with_target(preview, label="Another label")

    # Integrated and content-integrated are different gates; neither the
    # consequences nor a label a person read may change unannounced.
    assert content.fingerprint != preview.fingerprint
    assert worded.fingerprint != preview.fingerprint
    assert labelled.fingerprint != preview.fingerprint
    assert retained_choices(preview, worded, (target.identity,)) == ()


def test_the_fingerprint_excludes_only_the_named_narration(tmp_path: Path) -> None:
    preview = integrated_preview(tmp_path)
    target = preview.targets[0]
    blocked = with_target(
        preview,
        blockers=(CleanupBlocker(kind="locked", detail="locked: pid 1", command="a"),),
    )

    fetched = with_target(preview, observed_at="2026-10-05T00:00:00Z")
    renarrated = with_target(
        blocked,
        blockers=(CleanupBlocker(kind="locked", detail="locked: pid 2", command="b"),),
    )
    regated = with_target(
        blocked,
        blockers=(CleanupBlocker(kind="dirty", detail="locked: pid 1", command="a"),),
    )

    assert fetched.fingerprint == preview.fingerprint
    assert renarrated.fingerprint == blocked.fingerprint
    assert regated.fingerprint != blocked.fingerprint
    assert disclosed_facts(fetched.targets[0]) == disclosed_facts(target)
    assert retained_choices(preview, fetched, (target.identity,)) == (target.identity,)


def test_a_branch_whose_integration_changed_is_confirmed_again(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    request = BranchCleanupRequest(root, "feat")
    preview = inspect_cleanup(request)
    # The Branch is squash-merged rather than reachable: main moves on to a
    # commit holding the same content.
    git(root, "reset", "-q", "--hard", "HEAD~1")
    git(root, "merge", "-q", "--squash", "feat")
    git(root, "commit", "-q", "-m", "squash feat")
    git(root, "update-ref", "refs/remotes/origin/main", "main")

    report = perform_cleanup(confirm(request, preview, LOCAL_FEAT))

    assert report.changed is True
    assert report.refusals == (CHANGED_SINCE_PREVIEW,)
    revised = by_identity(report.preview)[LOCAL_FEAT]
    assert revised.integration is not None
    assert revised.integration.content_integrated is True
    git(root, "rev-parse", "--verify", "refs/heads/feat")


# --- Commands a person can paste ---------------------------------------------

HOSTILE = "fix$(touch${IFS}pwned)"


def test_shell_commands_quote_every_argument(tmp_path: Path) -> None:
    spaced = tmp_path / "a dir"
    command = shell_command("git", "-C", spaced, "branch", "-d", HOSTILE)

    assert shlex.split(command) == ["git", "-C", str(spaced), "branch", "-d", HOSTILE]
    assert shlex.split(in_directory(spaced, "dashpot", "work", "stop")) == [
        "cd",
        str(spaced),
        "&&",
        "dashpot",
        "work",
        "stop",
    ]


def test_a_hostile_branch_name_and_a_spaced_path_are_shown_quoted(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, HOSTILE)
    worktree = tmp_path / "my wt"
    git(root, "worktree", "add", "-q", str(worktree), HOSTILE)
    (worktree / "scratch.txt").write_text("")
    resolved = worktree.resolve()

    preview = preview_worktree(root, worktree)

    tree, local = preview.targets[:2]
    commands = {
        blocker.kind: blocker.command for blocker in (*tree.blockers, *local.blockers)
    }
    assert commands["dirty"] == f"git -C '{resolved}' status"
    assert commands["unintegrated"] == (
        f"git log --oneline 'refs/remotes/origin/main..refs/heads/{HOSTILE}'"
    )
    for command in filter(None, commands.values()):
        run_shell(command, root)
    assert not list(tmp_path.rglob("pwned"))
    report = check_worktree(root, worktree)
    assert report.remove_commands == (
        f"git worktree remove '{resolved}'",
        f"git branch -d '{HOSTILE}'",
    )


# --- Orphaned Agent Runs ------------------------------------------------------


def run_on(worktree: Path, *, relocation: RelocationIntent | None) -> ActiveWork:
    return ActiveWork(
        session_key="codex-4242-deadbeef",
        harness="codex",
        session_label=f"Codex session {THREAD}",
        session_process=SessionProcess(pid=CODEX.pid, started_at=CODEX.started_at),
        issue_id="I_10",
        issue_reference="issue-10",
        binding_provenance="explicit-reference",
        started_at="2026-09-30T03:35:00.000000Z",
        working_directory=str(worktree),
        branch="feat",
        session_id=THREAD,
        relocation=relocation,
    )


@pytest.mark.parametrize(
    ("liveness", "relocating", "orphaned"),
    [
        ("gone", False, True),
        ("gone", True, False),
        ("live", False, False),
        ("unknown", False, False),
    ],
)
def test_only_a_gone_run_not_relocating_is_orphaned(
    tmp_path: Path, liveness: SessionLiveness, relocating: bool, orphaned: bool
) -> None:
    relocation = (
        RelocationIntent(str(tmp_path / "next"), "2026-09-30T03:40:00Z")
        if relocating
        else None
    )
    work = run_on(tmp_path, relocation=relocation)
    probed: list[SessionProcess] = []

    def observe(process: SessionProcess) -> LivenessObservation:
        probed.append(process)
        return LivenessObservation(liveness)

    found = orphaned_process(work, observe)

    assert (found is not None) is orphaned
    # A relocating run is not probed at all; any other is probed as recorded.
    assert probed == ([] if relocating else [work.session_process])


def test_a_relocating_run_is_worded_as_moving_not_orphaned(tmp_path: Path) -> None:
    worktree, worktrees = occupied_worktree(tmp_path, "codex", THREAD, CODEX)
    target = tmp_path / "next wt"
    relocation = RelocationIntent(str(target), "2026-09-30T03:40:00Z")
    WorkStore(worktree).start(run_on(worktree, relocation=relocation))

    blockers = assess_worktree_occupancy(worktree, worktrees, absent())

    (blocker,) = [one for one in blockers if one.kind == "agent-run"]
    stop = f"cd {worktree} && dashpot work stop --session codex-4242-deadbeef"
    assert blocker.detail == (
        f"Codex session {THREAD} is relocating its Agent Run on issue-10 to "
        f"{target}: once its client exits, resume that session there, which "
        f"carries the run with it. If the relocation was abandoned, end the run "
        f"with: {stop}"
    )
    assert blocker.command == f"codex resume {THREAD} -C '{target}'"
    assert "Orphaned" not in blocker.detail


# --- Locks, nested records, and protection -----------------------------------


def test_the_production_adapter_probes_the_lock_holder(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    git(root, "worktree", "lock", "--reason", f"pid {os.getpid()}", str(worktree))

    preview = GitCleanupAdapter(timeout=10).inspect(
        WorktreeCleanupRequest(root, worktree), protected=()
    )

    (locked,) = [one for one in preview.targets[0].blockers if one.kind == "locked"]
    assert locked.detail == f"locked: pid {os.getpid()} (holding process live)"


def test_a_stale_locked_record_inside_is_unlocked_then_pruned(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    ignore_claude(root)
    nested = nest_worktree(root, worktree, "inner")
    git(root, "worktree", "lock", str(nested))
    shutil.rmtree(nested)
    request = WorktreeCleanupRequest(root, worktree)

    (blocker,) = inspect_cleanup(request).targets[0].blockers
    # A plain prune leaves a locked record alone.
    git(root, "worktree", "prune")
    still = inspect_cleanup(request).targets[0]
    assert blocker.command is not None
    run_shell(blocker.command, root)
    pruned = inspect_cleanup(request).targets[0]

    assert blocker == CleanupBlocker(
        kind="nested-worktree",
        detail=f"a stale, locked record of the Worktree {nested}, whose directory "
        "is gone, is inside this one: unlock it, then prune it, since prune leaves "
        "a locked record alone",
        command=f"git worktree unlock {nested} && git worktree prune",
    )
    assert kinds(still) == {"nested-worktree"}
    assert pruned.available is True


def test_worktree_check_protects_what_a_cleanup_protects(tmp_path: Path) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")
    # A configured anchor named from inside the Worktree is taken at its root.
    protected = protected_checkouts([worktree / ".venv"])

    report = check_worktree(root, worktree, protected=protected)
    preview = preview_worktree(root, worktree, protected=protected)

    assert worktree.resolve() in protected
    assert [one.kind for one in report.obstacles] == ["protected"]
    assert kinds(preview.targets[0]) == {"protected"}
    assert report.removable is False


def test_worktree_check_says_its_remove_commands_delete_ignored_paths(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    branch(root, "feat")
    integrate(root, "feat")
    worktree = linked(tmp_path, root, "feat")

    report = check_worktree(root, worktree)

    assert report.removable is True
    assert report.ignored == (".venv/",)
    lines = describe_removability(report)
    removal = lines.index("Remove with")
    assert lines[removal + 3] == (
        "  which also deletes 1 ignored path inside it, including any Dashpot "
        "state, hook records, and Work Store there"
    )


def test_a_gone_anchor_is_still_protected_where_it_was(tmp_path: Path) -> None:
    gone = tmp_path / "gone"

    protected = protected_checkouts([gone])

    assert protected[0] == Path.cwd().resolve()
    assert gone.resolve() in protected


def test_a_preview_target_carries_every_field_the_fingerprint_reads(
    tmp_path: Path,
) -> None:
    # A field added to a target later counts unless it is named an exclusion.
    root = repo(tmp_path)
    branch(root, "feat")
    target = by_identity(preview_branch(root, "feat"))[LOCAL_FEAT]
    facts = disclosed_facts(target)

    assert target.blockers
    assert set(facts) == set(target.model_dump()) - {"observed_at"}
    assert [set(blocker) for blocker in facts["blockers"]] == [{"kind"}] * len(
        target.blockers
    )
