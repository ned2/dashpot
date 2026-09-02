"""The explicit fetch seam: one bounded, non-interactive fetch per remote."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dashpot.commands import non_interactive_runner
from dashpot.fetch import FETCH_ENVIRONMENT, fetch_remotes, remote_fetcher
from dashpot.git import Git
from factories import SequenceRunner, completed


def over(runner: SequenceRunner) -> Git:
    """A Git adapter over ``runner``; the fetch retargets it at the anchor."""
    return Git(Path("/unused"), timeout=7, runner=runner)


def test_fetches_and_prunes_every_configured_remote_in_git_order() -> None:
    runner = SequenceRunner(
        completed("upstream\norigin\n"), completed(""), completed("")
    )

    report = fetch_remotes(Path("/repo"), git=over(runner))

    assert report.succeeded
    assert report.fetched == ("upstream", "origin")
    assert report.summary() == "fetched and pruned upstream, origin"
    # One fetch per remote, in Git's order, at the anchor, under the timeout:
    # a single ``--all`` could not say which remote failed.
    assert [call[0] for call in runner.calls] == [
        ["git", "remote"],
        ["git", "fetch", "--prune", "--", "upstream"],
        ["git", "fetch", "--prune", "--", "origin"],
    ]
    assert {call[1] for call in runner.calls} == {Path("/repo")}
    assert {call[2] for call in runner.calls} == {7}


def test_no_configured_remote_is_a_refusal_not_a_fetch() -> None:
    runner = SequenceRunner(completed("\n"))

    report = fetch_remotes(Path("/repo"), git=over(runner))

    assert not report.succeeded
    assert report.refusal == "no remote is configured"
    assert report.summary() == "no remote is configured"
    assert len(runner.calls) == 1


def test_remotes_that_cannot_be_listed_are_a_refusal() -> None:
    runner = SequenceRunner(
        completed("", stderr="fatal: not a git repository", returncode=128)
    )

    report = fetch_remotes(Path("/repo"), git=over(runner))

    assert report.refusal == "cannot list remotes: fatal: not a git repository"
    assert report.remotes == ()


def test_one_failing_remote_does_not_make_the_fetch_a_success() -> None:
    runner = SequenceRunner(
        completed("origin\nfork\n"),
        completed(""),
        completed(
            "",
            stderr=(
                "remote: Invalid username or password.\n"
                "fatal: Authentication failed for 'https://example.test/fork'\n"
            ),
            returncode=128,
        ),
    )

    report = fetch_remotes(Path("/repo"), git=over(runner))

    assert not report.succeeded
    assert report.fetched == ("origin",)
    assert [(item.remote, item.ok) for item in report.remotes] == [
        ("origin", True),
        ("fork", False),
    ]
    assert report.summary() == (
        "fetched and pruned origin; failed fork: "
        "fatal: Authentication failed for 'https://example.test/fork'"
    )
    # The failure did not stop the fetch attempting every remote.
    assert len(runner.calls) == 3


def test_a_timed_out_remote_is_reported_and_the_rest_still_fetched() -> None:
    runner = SequenceRunner(
        completed("origin\nupstream\n"),
        RuntimeError("command timed out after 7s: git"),
        completed(""),
    )

    report = fetch_remotes(Path("/repo"), git=over(runner))

    assert not report.succeeded
    assert report.fetched == ("upstream",)
    assert report.summary() == (
        "fetched and pruned upstream; failed origin: command timed out after 7s: git"
    )


def test_every_remote_failing_reports_no_fetch() -> None:
    runner = SequenceRunner(
        completed("origin\n"), completed("", stderr="ssh: no route", returncode=128)
    )

    report = fetch_remotes(Path("/repo"), git=over(runner))

    assert report.fetched == ()
    assert report.summary() == "failed origin: ssh: no route"


def test_non_interactive_runner_denies_prompts_a_terminal() -> None:
    runner = non_interactive_runner(FETCH_ENVIRONMENT)
    script = (
        "import os, sys; "
        "print(os.environ['GIT_TERMINAL_PROMPT']); "
        "print(os.getsid(0) == os.getpid()); "
        "print(repr(sys.stdin.read()))"
    )

    result = runner([sys.executable, "-c", script], Path.cwd(), 10)

    # Git's own prompt is off, the command leads its own session so no helper
    # can open the controlling terminal, and stdin is already exhausted.
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["0", "True", "''"]
    assert "GIT_TERMINAL_PROMPT" not in os.environ


def test_the_production_fetcher_fetches_at_the_anchor_it_is_given(
    tmp_path: Path,
) -> None:
    # A repository with no remote proves the fetcher runs Git at the anchor
    # and refuses honestly, without touching the network.
    anchor = tmp_path / "repo"
    anchor.mkdir()
    Git(anchor).text("init", "-q")

    report = remote_fetcher(timeout=10)(anchor)

    assert report.anchor == str(anchor)
    assert report.refusal == "no remote is configured"
