"""Cleanup refuses to remove a Worktree a process is running inside (ADR 0104).

Each test gives the preview, ``worktree check``, or the confirmed removal a
fake scan of the host's process working directories, so no real process
decides an outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashpot import cli
from dashpot.repository.cleanup import (
    CHANGED_SINCE_PREVIEW,
    SUB_AGENT_SCOPE,
    CleanupBlocker,
    CleanupConfirmation,
    CleanupPreview,
    WorktreeCleanupRequest,
    describe_cleanup_preview,
    describe_cleanup_report,
    inspect_cleanup,
    perform_cleanup,
    unchecked_processes_note,
)
from dashpot.repository.worktrees.removability import (
    check_worktree,
    describe_removability,
)
from dashpot.serialization import cleanup_preview_document, removability_document
from dashpot.sessions import working_directories
from dashpot.sessions.working_directories import (
    ProcessDirectory,
    ProcessScan,
    ScanGap,
    WorkingDirectories,
)
from factories import git
from helpers import scan_of

SANDBOXED = (
    "Processes running inside this Worktree were not all checked: Dashpot runs "
    "inside a sandbox's process namespace and cannot see the processes outside "
    "it; check again from a shell outside the sandbox."
)


def repository_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A Repository on ``main`` and a clean linked Worktree on integrated ``feat``."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Sim\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "branch", "feat")
    worktree = tmp_path / "wt"
    git(root, "worktree", "add", "-q", str(worktree), "feat")
    return root, worktree.resolve()


def preview(root: Path, worktree: Path, scan: ProcessScan) -> CleanupPreview:
    return inspect_cleanup(WorktreeCleanupRequest(root, worktree), scan=scan)


def test_a_process_inside_the_worktree_blocks_its_removal(tmp_path: Path) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    server = ProcessDirectory(4242, 1, "node", worktree / "web")

    tree, local = preview(root, worktree, scan_of(server)).targets

    assert tree.blockers == (
        CleanupBlocker(
            kind="process",
            detail=f"A process is running inside this Worktree: pid 4242 (node) "
            f"at {worktree / 'web'}. Removing the Worktree would delete the "
            "directory it works in: end it or move it out of the Worktree.",
            command="ps -ww -o pid=,args= -p 4242",
        ),
    )
    # The Branch stays checked out in a Worktree that cannot go.
    assert [blocker.kind for blocker in local.blockers] == ["checked-out"]


def test_one_blocker_names_many_processes_and_keeps_the_fingerprint(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    shells = [ProcessDirectory(100 + n, 1, "bash", worktree) for n in range(7)]

    many = preview(root, worktree, scan_of(*shells))
    one = preview(root, worktree, scan_of(shells[0]))

    (blocker,) = many.targets[0].blockers
    assert blocker.detail.startswith(
        f"7 processes are running inside this Worktree: pid 100 (bash) at "
        f"{worktree}; pid 101 (bash) at {worktree}; "
    )
    assert f"pid 104 (bash) at {worktree}; and 2 more. Removing" in blocker.detail
    assert "pid 105" not in blocker.detail
    assert blocker.detail.endswith("end them or move them out of the Worktree.")
    assert blocker.command == "ps -ww -o pid=,args= -p 100,101,102,103,104,105,106"
    # A process starting or ending beside another changes no blocker.
    assert many.fingerprint == one.fingerprint


def test_a_process_outside_the_worktree_blocks_nothing(tmp_path: Path) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    elsewhere = ProcessDirectory(4242, 1, "bash", root)

    tree, _local = preview(root, worktree, scan_of(elsewhere)).targets

    assert tree.available is True


def test_finding_no_process_clears_no_other_blocker(tmp_path: Path) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    (worktree / "scratch.txt").write_text("unsaved\n")

    tree, _local = preview(root, worktree, scan_of()).targets

    assert [blocker.kind for blocker in tree.blockers] == ["dirty"]


def test_the_main_worktree_is_not_scanned(tmp_path: Path) -> None:
    root, _worktree = repository_with_worktree(tmp_path)

    def refuse() -> WorkingDirectories:
        raise AssertionError("the main Worktree was scanned")

    tree = preview(root, root, refuse).targets[0]

    assert "process" not in {blocker.kind for blocker in tree.blockers}


def test_a_process_that_arrives_after_the_preview_refuses_the_removal(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    request = WorktreeCleanupRequest(root, worktree)
    shown = inspect_cleanup(request, scan=scan_of())
    identity = shown.targets[0].identity
    confirmation = CleanupConfirmation(request, shown.fingerprint, (identity,))
    shell = ProcessDirectory(4242, 1, "bash", worktree)

    refused = perform_cleanup(confirmation, scan=scan_of(shell))

    assert refused.performed is False
    assert refused.refusals == (CHANGED_SINCE_PREVIEW,)
    assert refused.preview.targets[0].blockers[0].kind == "process"
    assert worktree.exists()

    removed = perform_cleanup(confirmation, scan=scan_of())

    assert removed.succeeded is True
    assert not worktree.exists()


def test_an_incomplete_scan_is_stated_beneath_a_removable_worktree(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    request = WorktreeCleanupRequest(root, worktree)

    shown = inspect_cleanup(request, scan=scan_of(incomplete="isolated-namespace"))

    assert shown.targets[0].available is True
    assert shown.unchecked_processes == SANDBOXED
    assert unchecked_processes_note(shown) == SANDBOXED
    lines = describe_cleanup_preview(shown)
    scope = lines.index(f"      {SUB_AGENT_SCOPE}")
    assert lines[scope + 1] == f"      {SANDBOXED}"
    assert cleanup_preview_document(shown)["uncheckedProcesses"] == SANDBOXED

    dry_run = perform_cleanup(
        CleanupConfirmation(request, shown.fingerprint, (shown.targets[0].identity,)),
        scan=scan_of(incomplete="isolated-namespace"),
        dry_run=True,
    )
    assert f"     {SANDBOXED}" in describe_cleanup_report(dry_run)


def test_a_scan_that_falls_short_only_at_confirmation_refuses_the_removal(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    request = WorktreeCleanupRequest(root, worktree)
    shown = inspect_cleanup(request, scan=scan_of())
    confirmation = CleanupConfirmation(
        request, shown.fingerprint, (shown.targets[0].identity,)
    )

    refused = perform_cleanup(confirmation, scan=scan_of(incomplete="lsof-timeout"))

    assert refused.performed is False
    assert refused.refusals == (CHANGED_SINCE_PREVIEW,)
    assert refused.preview.unchecked_processes == (
        "Processes running inside this Worktree were not all checked: lsof did "
        "not answer in time."
    )
    assert worktree.exists()


def test_a_performed_removal_states_the_check_it_went_ahead_on(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    request = WorktreeCleanupRequest(root, worktree)
    gap = scan_of(incomplete="isolated-namespace")
    shown = inspect_cleanup(request, scan=gap)

    removed = perform_cleanup(
        CleanupConfirmation(request, shown.fingerprint, (shown.targets[0].identity,)),
        scan=gap,
    )

    assert removed.succeeded is True
    lines = describe_cleanup_report(removed)
    deleted = next(index for index, line in enumerate(lines) if "deleted" in line)
    assert lines[deleted + 1] == f"      removed {worktree}"
    assert lines[deleted + 2].startswith("      recover: git worktree add ")
    assert lines[deleted + 3] == f"      {SANDBOXED}"


def test_a_sandboxed_scan_still_blocks_on_the_processes_it_sees(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    shell = ProcessDirectory(7, 1, "bash", worktree)

    shown = preview(root, worktree, scan_of(shell, incomplete="isolated-namespace"))

    assert shown.targets[0].blockers[0].kind == "process"
    # A blocked Worktree claims no absence of occupants, so says no gap.
    assert unchecked_processes_note(shown) is None
    assert SANDBOXED not in "\n".join(describe_cleanup_preview(shown))


@pytest.mark.parametrize(
    ("reason", "why"),
    [
        ("proc-unreadable", "/proc could not be read"),
        ("lsof-unavailable", "this host has no /proc, and lsof could not be run"),
        ("lsof-timeout", "lsof did not answer in time"),
        ("lsof-failed", "lsof failed"),
    ],
)
def test_each_reason_a_scan_falls_short_is_said_in_words(
    tmp_path: Path, reason: ScanGap, why: str
) -> None:
    root, worktree = repository_with_worktree(tmp_path)

    shown = preview(root, worktree, scan_of(incomplete=reason))

    assert shown.unchecked_processes == (
        f"Processes running inside this Worktree were not all checked: {why}."
    )


def test_worktree_check_reports_the_process_and_states_an_incomplete_scan(
    tmp_path: Path,
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    shell = ProcessDirectory(4242, 1, "bash", worktree)

    blocked = check_worktree(root, worktree, scan=scan_of(shell))
    removable = check_worktree(
        root, worktree, scan=scan_of(incomplete="isolated-namespace")
    )

    assert blocked.removable is False
    assert [obstacle.kind for obstacle in blocked.obstacles] == ["process"]
    assert "  - process: A process is running inside this Worktree: pid 4242" in (
        "\n".join(describe_removability(blocked))
    )
    assert removable.removable is True
    assert removable.unchecked_processes == SANDBOXED
    assert describe_removability(removable)[3:5] == [
        f"           {SUB_AGENT_SCOPE}",
        f"           {SANDBOXED}",
    ]
    assert removability_document(removable)["uncheckedProcesses"] == SANDBOXED
    assert removability_document(blocked)["uncheckedProcesses"] is None


def test_the_command_line_reads_the_host_scan_for_check_and_remove(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, worktree = repository_with_worktree(tmp_path)
    monkeypatch.chdir(root)
    shell = ProcessDirectory(4242, 1, "bash", worktree)
    monkeypatch.setattr(working_directories, "host_working_directories", scan_of(shell))

    assert cli.main(["worktree", "check", str(worktree), "--json"]) == 0
    (obstacle,) = json.loads(capsys.readouterr().out)["obstacles"]
    assert obstacle["kind"] == "process"

    assert cli.main(["worktree", "remove", str(worktree)]) != 0
    out = capsys.readouterr().out
    assert "Worktree is unavailable: A process is running inside this Worktree" in out
    assert worktree.exists()
