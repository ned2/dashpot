from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast
from unittest import mock

from dashpot.commands import CommandResult
from dashpot.model import Diagnostic
from dashpot.repository import LockHolder, observe_observation_targets
from factories import git


class SequenceRunner:
    def __init__(self, *results: CommandResult | Exception) -> None:
        self.results = iter(results)
        self.calls: list[tuple[list[str], Path, float]] = []

    def __call__(self, args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        self.calls.append((list(args), cwd, timeout))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult([], returncode, stdout, stderr)


def test_observes_main_and_linked_targets_from_nul_porcelain(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main"
    linked = tmp_path / "linked"
    main.mkdir()
    linked.mkdir()
    porcelain = (
        f"worktree {main}\0"
        "HEAD abc123\0"
        "branch refs/heads/main\0\0"
        f"worktree {linked}\0"
        "HEAD def456\0"
        "detached\0\0"
    )
    runner = SequenceRunner(
        completed(porcelain),
        completed(),
        completed(" M changed.py\n"),
    )
    times = iter([1.0, 1.004, 2.0, 2.009])

    inventory = observe_observation_targets(
        [main], runner=runner, clock=lambda: next(times)
    )

    assert inventory.diagnostics == ()
    assert [target.path for target in inventory.targets] == [str(main), str(linked)]
    assert inventory.targets[0].branch == "main"
    assert inventory.targets[0].detached is False
    assert inventory.targets[0].head == "abc123"
    assert inventory.targets[0].dirty is False
    assert inventory.targets[0].availability == "available"
    assert inventory.targets[0].elapsed_ms == 4
    assert inventory.targets[0].role == "main"
    assert inventory.targets[1].role == "linked"
    assert inventory.targets[1].branch is None
    assert inventory.targets[1].detached is True
    assert inventory.targets[1].dirty is True
    assert inventory.targets[1].elapsed_ms == 9
    assert [call[0] for call in runner.calls] == [
        ["git", "worktree", "list", "--porcelain", "-z"],
        ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
        ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
    ]


def test_a_lock_is_reported_only_once_its_holder_is_gone(tmp_path: Path) -> None:
    worktree = tmp_path / "held"
    worktree.mkdir()
    porcelain = (
        f"worktree {worktree}\0HEAD aaa111\0branch refs/heads/main\0"
        "locked claude session cyclopts-cli (pid 1699806 start 8792235)\0\0"
    )

    def observe(holder: str) -> Sequence[Diagnostic]:
        runner = SequenceRunner(completed(porcelain), completed())
        times = iter([1.0, 1.001])
        inventory = observe_observation_targets(
            [worktree],
            runner=runner,
            clock=lambda: next(times),
            process_lookup=lambda pid: (
                cast("LockHolder", holder) if pid == 1699806 else "gone"
            ),
        )
        return inventory.targets[0].diagnostics

    # A session holding its own Worktree is the steady state, not a report.
    assert observe("live") == ()

    # A lock that outlived its session keeps the Worktree from being pruned.
    stale = observe("gone")
    assert [item.code for item in stale] == ["target-locked-stale"]
    assert stale[0].severity == "warning"

    # Dashpot never claims a lock is stale on a process it could not observe.
    unobservable = observe("unknown")
    assert [item.code for item in unobservable] == ["target-locked"]
    assert unobservable[0].severity == "info"


def test_an_unattributed_lock_stays_an_observation(tmp_path: Path) -> None:
    worktree = tmp_path / "held"
    worktree.mkdir()
    porcelain = (
        f"worktree {worktree}\0HEAD aaa111\0branch refs/heads/main\0"
        "locked maintenance\0\0"
    )
    times = iter([1.0, 1.001])

    inventory = observe_observation_targets(
        [worktree],
        runner=SequenceRunner(completed(porcelain), completed()),
        clock=lambda: next(times),
        process_lookup=lambda _pid: "gone",
    )

    # No process is named, so there is no holder to have exited.
    assert [item.code for item in inventory.targets[0].diagnostics] == ["target-locked"]


def test_preserves_locked_prunable_and_missing_targets_but_excludes_bare(
    tmp_path: Path,
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    prunable = tmp_path / "prunable"
    missing = tmp_path / "missing"
    bare = tmp_path / "bare.git"
    bare.mkdir()
    porcelain = (
        f"worktree {locked}\0HEAD aaa111\0branch refs/heads/main\0"
        "locked maintenance\0\0"
        f"worktree {prunable}\0HEAD bbb222\0branch refs/heads/old\0"
        "prunable gitdir file points to non-existent location\0\0"
        f"worktree {missing}\0HEAD ccc333\0detached\0\0"
        f"worktree {bare}\0HEAD ddd444\0bare\0\0"
    )
    runner = SequenceRunner(completed(porcelain), completed())
    times = iter([1.0, 1.001])

    inventory = observe_observation_targets(
        [locked], runner=runner, clock=lambda: next(times)
    )

    assert [target.path for target in inventory.targets] == [
        str(locked),
        str(prunable),
        str(missing),
    ]
    by_path = {target.path: target for target in inventory.targets}
    assert by_path[str(locked)].availability == "available"
    assert [item.code for item in by_path[str(locked)].diagnostics] == ["target-locked"]
    assert by_path[str(prunable)].availability == "unavailable"
    assert [item.code for item in by_path[str(prunable)].diagnostics] == [
        "target-prunable"
    ]
    assert by_path[str(missing)].availability == "unavailable"
    assert [item.code for item in by_path[str(missing)].diagnostics] == [
        "target-missing"
    ]
    # Retained unavailable targets keep the role Git reported for them.
    assert by_path[str(locked)].role == "main"
    assert by_path[str(prunable)].role == "linked"
    assert by_path[str(missing)].role == "linked"
    assert [item.code for item in inventory.diagnostics] == ["target-bare"]
    assert len(runner.calls) == 2


def test_combines_all_anchors_deduplicates_paths_and_isolates_discovery_failure(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    linked = tmp_path / "linked\nwith-newline"
    failed = tmp_path / "failed"
    first.mkdir()
    second.mkdir()
    linked.mkdir()
    failed.mkdir()
    first_porcelain = (
        f"worktree {first}\0HEAD aaa111\0branch refs/heads/main\0\0"
        f"worktree {linked}\0HEAD bbb222\0detached\0future value\0\0"
    )
    second_porcelain = (
        f"worktree {second}\0HEAD ccc333\0branch refs/heads/main\0\0"
        f"worktree {linked}\0HEAD bbb222\0detached\0\0"
    )
    runner = SequenceRunner(
        completed(first_porcelain),
        completed(second_porcelain),
        RuntimeError("git timed out"),
        completed(),
        completed(),
        completed(),
    )

    inventory = observe_observation_targets([first, second, failed], runner=runner)

    assert [target.path for target in inventory.targets] == [
        str(first),
        str(linked),
        str(second),
    ]
    # Each listing names its own main working tree first; the role comes
    # from that ordering, never from the path's name.
    assert [target.role for target in inventory.targets] == [
        "main",
        "linked",
        "main",
    ]
    assert [item.code for item in inventory.diagnostics] == ["target-discovery"]


def test_malformed_records_remain_diagnostic_without_becoming_executable(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    porcelain = f"HEAD no-path\0detached\0\0worktree {malformed}\0HEAD abc123\0\0"
    runner = SequenceRunner(completed(porcelain))

    inventory = observe_observation_targets([tmp_path], runner=runner)

    assert [item.code for item in inventory.diagnostics] == ["target-malformed"]
    assert inventory.targets[0].availability == "unavailable"
    assert inventory.targets[0].diagnostics[0].code == "target-malformed"
    assert len(runner.calls) == 1


def test_real_git_inventory_tracks_linked_worktree_runtime_lifecycle(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main"
    linked = tmp_path / "linked"
    main.mkdir()
    git(main, "init")
    git(main, "config", "user.email", "dashpot@example.invalid")
    git(main, "config", "user.name", "Dashpot Tests")
    (main / "tracked.txt").write_text("base\n")
    git(main, "add", "tracked.txt")
    git(main, "commit", "-m", "initial")
    git(main, "worktree", "add", "-b", "feature", str(linked))

    clean = observe_observation_targets([main])
    (linked / "untracked.txt").write_text("change\n")
    dirty = observe_observation_targets([main])
    git(main, "worktree", "remove", "--force", str(linked))
    removed = observe_observation_targets([main])

    assert [target.path for target in clean.targets] == [str(main), str(linked)]
    assert [target.role for target in clean.targets] == ["main", "linked"]
    assert {target.path: target.dirty for target in clean.targets}[str(linked)] is False
    assert {target.path: target.dirty for target in dirty.targets}[str(linked)] is True
    assert [target.path for target in removed.targets] == [str(main)]


def test_unstatable_target_is_inaccessible_not_missing(tmp_path: Path) -> None:
    target = tmp_path / "protected"
    target.mkdir()
    porcelain = f"worktree {target}\0HEAD abc123\0branch refs/heads/main\0\0"
    runner = SequenceRunner(completed(porcelain))

    with mock.patch.object(Path, "stat", side_effect=PermissionError("denied")):
        inventory = observe_observation_targets([tmp_path], runner=runner)

    assert inventory.targets[0].availability == "unavailable"
    assert inventory.targets[0].diagnostics[0].code == "target-inaccessible"
    assert len(runner.calls) == 1
