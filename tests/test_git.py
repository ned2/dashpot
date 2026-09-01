from __future__ import annotations

from pathlib import Path

import pytest

from dashpot.commands import CommandResult
from dashpot.git import Git, GitError
from factories import SequenceRunner, completed


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
    git, _runner = adapter(RuntimeError("command not found: git"))

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
        RuntimeError("command timed out after 5s: git"),
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
