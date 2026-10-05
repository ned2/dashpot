from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from dashpot.core.commands import CommandError, CommandResult
from dashpot.core.distribution import source_dirty
from dashpot.core.git import MUTATION_TIMEOUT, Git, GitError
from dashpot.repository import fetch
from dashpot.repository.cleanup import (
    BranchCleanupRequest,
    CleanupConfirmation,
    inspect_cleanup,
    perform_cleanup,
)
from dashpot.repository.cleanup.perform import cleanup_git
from dashpot.repository.fetch import remote_fetcher
from dashpot.repository.observe import observe_branches, observe_observation_targets
from factories import SequenceRunner, completed, git


def adapter(
    *results: CommandResult | Exception, root: Path = Path("/repo")
) -> tuple[Git, SequenceRunner]:
    runner = SequenceRunner(*results)
    return Git(root, runner=runner), runner


def test_run_prefixes_git_and_carries_root_and_timeout() -> None:
    git, runner = adapter(completed("ok\n"))

    result = git.run("status", "--porcelain=v1")

    assert result.stdout == "ok\n"
    assert runner.calls == [(["git", "status", "--porcelain=v1"], Path("/repo"), 5)]


def test_run_returns_a_non_zero_exit_for_the_caller_to_read() -> None:
    git, _runner = adapter(completed(stderr="boom", returncode=1))

    assert git.run("show", "x").returncode == 1


def test_run_wraps_a_runner_failure_as_a_git_error() -> None:
    git, _runner = adapter(CommandError("command not found: git"))

    with pytest.raises(GitError) as caught:
        git.run("status")

    assert caught.value.detail == "command not found: git"
    assert caught.value.argv == ("status",)
    assert caught.value.cwd == Path("/repo")
    assert str(caught.value) == "git status failed: command not found: git"


def test_at_retargets_the_root_and_optionally_the_timeout() -> None:
    git, runner = adapter(completed(), completed())

    git.at(Path("/elsewhere")).run("status")
    git.at(Path("/slow"), timeout=2).run("status")

    assert [(call[1], call[2]) for call in runner.calls] == [
        (Path("/elsewhere"), 5),
        (Path("/slow"), 2),
    ]


def test_text_strips_stdout_and_raises_on_a_non_zero_exit() -> None:
    git, _runner = adapter(
        completed("  main  \n"), completed(stderr="bad\n", returncode=128)
    )

    assert git.text("symbolic-ref", "HEAD") == "main"
    with pytest.raises(GitError, match=r"git rev-parse HEAD failed: bad"):
        git.text("rev-parse", "HEAD")


def test_text_reports_the_exit_code_when_stderr_is_silent() -> None:
    git, _runner = adapter(completed(returncode=3))

    with pytest.raises(GitError, match=r"failed: exit 3"):
        git.text("show", "x")


def test_maybe_is_none_only_on_a_clean_non_zero_exit() -> None:
    git, _runner = adapter(
        completed("value\n"),
        completed(returncode=1),
        CommandError("command timed out after 5s: git"),
    )

    assert git.maybe("rev-parse", "a") == "value"
    assert git.maybe("rev-parse", "b") is None
    # Failure is not absence: a timeout or missing binary still raises.
    with pytest.raises(GitError):
        git.maybe("rev-parse", "c")


def test_count_guards_the_integer_and_keeps_failure_distinct() -> None:
    git, _runner = adapter(
        completed("4\n"), completed("not-a-number\n"), completed(returncode=1)
    )

    assert git.count("rev-list", "--count", "a..b") == 4
    assert git.count("rev-list", "--count", "a..b") is None
    assert git.count("rev-list", "--count", "a..b") is None


def test_records_yields_fixed_arity_tuples_across_newlines_in_values() -> None:
    stream = (
        "refs/heads/main\0aaa\0/repo\0\nrefs/heads/odd\0bbb\0/linked\nwith-newline\0\n"
    )
    git, runner = adapter(completed(stream))

    listed = git.records(
        "refs/heads", fields=("%(refname)", "%(objectname)", "%(worktreepath)")
    )

    assert listed == [
        ("refs/heads/main", "aaa", "/repo"),
        ("refs/heads/odd", "bbb", "/linked\nwith-newline"),
    ]
    assert runner.calls[0][0] == [
        "git",
        "for-each-ref",
        "--format=%(refname)%00%(objectname)%00%(worktreepath)%00",
        "refs/heads",
    ]


def test_records_of_an_empty_listing_is_empty() -> None:
    git, _runner = adapter(completed(""))

    assert git.records("refs/heads", fields=("%(refname)",)) == []


def test_records_drops_a_truncated_final_record() -> None:
    stream = "refs/heads/main\0aaa\0\nrefs/heads/cut"
    git, _runner = adapter(completed(stream))

    listed = git.records("refs/heads", fields=("%(refname)", "%(objectname)"))

    assert listed == [("refs/heads/main", "aaa")]


def test_worktree_records_parses_the_nul_porcelain() -> None:
    porcelain = (
        "worktree /main\0HEAD abc\0branch refs/heads/main\0\0"
        "worktree /linked\0HEAD def\0detached\0locked reason here\0\0"
    )
    git, runner = adapter(completed(porcelain))

    records = git.worktree_records()

    assert records == [
        {"worktree": "/main", "HEAD": "abc", "branch": "refs/heads/main"},
        {
            "worktree": "/linked",
            "HEAD": "def",
            "detached": "",
            "locked": "reason here",
        },
    ]
    assert runner.calls[0][0] == ["git", "worktree", "list", "--porcelain", "-z"]


# --- Optional locks ----------------------------------------------------------


def _run_with_default_adapter(root: Path) -> None:
    Git(root).run("status", "--porcelain=v1")


def _run_with_cleanup_preview(root: Path) -> None:
    cleanup_git(root, 10, preview=True).run("status", "--porcelain=v1")


def _run_with_confirmed_cleanup(root: Path) -> None:
    cleanup_git(root, 10).run("status", "--porcelain=v1")


def _run_a_remote_fetch(root: Path) -> None:
    # The stand-in lists ``origin`` for ``git remote``, so ``git fetch`` runs too.
    remote_fetcher(10)(root)


def _ask_whether_the_source_is_dirty(root: Path) -> None:
    source_dirty(root)


@pytest.mark.parametrize(
    ("invoke", "subcommands"),
    [
        (_run_with_default_adapter, ["status"]),
        (_run_with_cleanup_preview, ["status"]),
        (_run_with_confirmed_cleanup, ["status"]),
        (_run_a_remote_fetch, ["remote", "fetch"]),
        (_ask_whether_the_source_is_dirty, ["status"]),
    ],
)
def test_production_git_adapters_turn_optional_locks_off(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invoke: Callable[[Path], None],
    subcommands: list[str],
) -> None:
    # A stand-in ``git`` first on PATH records the environment each production
    # adapter hands it, so the assertion reaches past the runner to the process.
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    recorded = tmp_path / "recorded"
    stand_in = bin_directory / "git"
    stand_in.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        f"with open({str(recorded)!r}, 'a') as log:\n"
        "    print(sys.argv[1], os.environ.get('GIT_OPTIONAL_LOCKS', 'unset'), "
        "file=log)\n"
        "if sys.argv[1:] == ['remote']:\n"
        "    print('origin')\n"
    )
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_directory}:{os.environ['PATH']}")
    # An inherited setting does not turn the optional locks back on.
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "1")

    invoke(tmp_path)

    calls = [line.split() for line in recorded.read_text().splitlines()]
    assert [subcommand for subcommand, _ in calls] == subcommands
    assert {locks for _, locks in calls} == {"0"}


# --- Named mutations and undecodable output ----------------------------------


def test_a_confirmed_cleanup_is_bounded_as_a_mutation_and_its_preview_is_not() -> None:
    root = Path("/repo")
    assert cleanup_git(root, 10).timeout == MUTATION_TIMEOUT
    assert cleanup_git(root, 10, preview=True).timeout == 10
    # A Git timeout longer than the floor still holds.
    assert cleanup_git(root, 900).timeout == 900


def test_a_remote_fetch_is_bounded_as_a_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapters: list[Git] = []

    def capturing(anchor: Path, *, git: Git) -> None:
        adapters.append(git)

    monkeypatch.setattr(fetch, "fetch_remotes", capturing)

    remote_fetcher(10)(Path("/repo"))

    (git,) = adapters
    assert git.timeout == MUTATION_TIMEOUT
    # Rooted at the anchor it fetches, not at the working directory.
    assert git.root == Path("/repo")


def _fetch_remotes(root: Path) -> object:
    return remote_fetcher(10)(root).refusal


def _observe_targets(root: Path) -> object:
    return [
        target.availability for target in observe_observation_targets([root]).targets
    ]


def _observe_branches(root: Path) -> object:
    return [branch.refname for branch in observe_branches([root]).branches]


def _preview_cleanup(root: Path) -> object:
    return inspect_cleanup(BranchCleanupRequest(root, "absent")).refusals


def _perform_cleanup(root: Path) -> object:
    request = BranchCleanupRequest(root, "absent")
    preview = inspect_cleanup(request)
    confirmation = CleanupConfirmation(request, preview.fingerprint, ())
    return perform_cleanup(confirmation).refusals


@pytest.mark.parametrize(
    ("invoke", "answer"),
    [
        (_fetch_remotes, "no remote is configured"),
        (_observe_targets, ["available"]),
        (_observe_branches, ["refs/heads/main"]),
        (_preview_cleanup, ("no Branch named absent at {root}",)),
        (
            _perform_cleanup,
            ("no Branch named absent at {root}", "no target is selected"),
        ),
    ],
)
def test_git_adapters_built_by_default_need_no_working_directory(
    git_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invoke: Callable[[Path], object],
    answer: object,
) -> None:
    git(git_repository, "commit", "-q", "--allow-empty", "-m", "start")
    root = git_repository.resolve()
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()

    expected = (
        tuple(each.format(root=root) for each in answer)
        if isinstance(answer, tuple)
        else answer
    )
    assert invoke(root) == expected


def test_a_ref_name_that_is_not_utf8_is_read_not_raised(tmp_path: Path) -> None:
    # Git stores a ref name as bytes; one in a legacy encoding must not fail
    # the listing it is in. It is packed so no file system has to name it.
    root = tmp_path / "repo"
    root.mkdir()
    identity = ["-c", "user.name=Sim", "-c", "user.email=sim@example.invalid"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(
        ["git", *identity, "commit", "-q", "--allow-empty", "-m", "start"],
        cwd=root,
        check=True,
    )
    head = Git(root).text("rev-parse", "HEAD")
    (root / ".git" / "packed-refs").write_bytes(
        b"# pack-refs with: peeled fully-peeled sorted \n"
        + f"{head} ".encode()
        + b"refs/heads/caf\xe9\n"
    )

    listed = Git(root).records("refs/heads", fields=("%(refname)",))

    assert sorted(listed) == [("refs/heads/caf�",), ("refs/heads/main",)]
