"""Pin observation documents and argument failures at the CLI seam."""

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from dashpot import cli
from factories import write_project_config
from test_github_issues import PROJECT_ID, REPOSITORY_ID
from test_github_pull_requests import pull_request_node
from test_runtime_spans import executable
from test_source_queries import (
    batch,
    context,
    github,
    hit,
    markdown,
    markdown_issue,
    node,
    reading,
    search,
)


@pytest.fixture(autouse=True)
def gh_calls(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Fail any test here that starts a ``gh`` process, real or not.

    The CLI reads ``configured_query_source`` through its own name, so a test
    that patches any other name gets the configured source instead, and a
    GitHub-backed configuration would reach the real ``gh`` (#331). A ``gh``
    first on ``PATH`` records each call and answers nothing.
    """
    directory = tmp_path_factory.mktemp("gh-guard")
    calls = directory / "calls"
    executable(
        directory,
        "gh",
        "import sys\n"
        f"with open({str(calls)!r}, 'a') as calls:\n"
        "    calls.write(' '.join(sys.argv[1:]) + '\\n')\n"
        "sys.exit(1)",
    )
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    yield calls
    assert not calls.exists(), f"a test started gh: {calls.read_text()}"


def test_a_github_source_the_cli_builds_itself_reaches_the_gh_guard(
    tmp_path, monkeypatch, capsys, gh_calls
):
    write_project_config(
        tmp_path,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        issue_source={"kind": "github"},
    )
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    cli.main(["issue", "list", "--json"])
    capsys.readouterr()
    # Unpatched, the CLI's own source starts gh, which the guard records.
    assert gh_calls.read_text().startswith("api graphql")
    gh_calls.unlink()


def test_list_json_keys_and_cross_invocation_cursor(tmp_path, monkeypatch, capsys):
    source = markdown(tmp_path)
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(cli, "configured_query_source", lambda *args, **kwargs: source)
    assert cli.main(["issue", "list", "--page-size", "1", "--compact-json"]) == 0
    output = capsys.readouterr()
    assert output.err == "" and output.out.count("\n") == 1
    document = json.loads(output.out)
    assert set(document) == {"page", "totals"}
    assert set(document["page"]) == {
        "context",
        "request",
        "effectiveOrdering",
        "status",
        "attemptedAt",
        "lastGoodAt",
        "diagnostics",
        "issues",
        "pullRequests",
        "auxiliary",
        "returnedCount",
        "matchedCount",
        "nextCursor",
        "continuation",
        "resultLimit",
    }
    assert document["totals"]["openCount"] == 3
    assert (
        cli.main(
            [
                "issue",
                "list",
                "--page-size",
                "1",
                "--cursor",
                document["page"]["nextCursor"],
                "--json",
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    assert second["page"]["issues"][0]["number"] == 2
    assert cli.main(["pr", "list", "--json"]) == 0
    unavailable = capsys.readouterr()
    assert unavailable.err == ""
    assert json.loads(unavailable.out)["page"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "args",
    [
        ["--page-size", "0"],
        ["--page-size", "101"],
        ["--state", "merged"],
        ["--cursor", "garbage"],
    ],
)
def test_invalid_list_arguments_stderr_and_exit_two(
    tmp_path, monkeypatch, capsys, args
):
    source = markdown(tmp_path)
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(cli, "configured_query_source", lambda *args, **kwargs: source)
    assert cli.main(["issue", "list", *args, "--json"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err


def test_ready_lists_the_open_issues_no_open_blocker_holds(
    tmp_path, monkeypatch, capsys
):
    source = markdown(tmp_path)
    directory = tmp_path / "issues"
    for path in directory.iterdir():
        path.unlink()
    markdown_issue(directory, 1)
    markdown_issue(directory, 2, blocked_by=["I_1"])
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(cli, "configured_query_source", lambda *args, **kwargs: source)
    assert cli.main(["issue", "list", "--state", "ready", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["page"]["request"]["state"] == "ready"
    assert [issue["number"] for issue in document["page"]["issues"]] == [1]
    assert document["page"]["auxiliary"]["I_1"]["openBlockers"] == []

    assert cli.main(["issue", "list", "--state", "all", "--json"]) == 0
    auxiliary = json.loads(capsys.readouterr().out)["page"]["auxiliary"]
    assert auxiliary["I_2"]["openBlockers"] == [
        {"id": "I_1", "reference": "issue-1", "number": 1}
    ]
    # Only an Issue can be Ready.
    assert cli.main(["pr", "list", "--state", "ready", "--json"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err


@pytest.mark.parametrize("command", ["issue", "pr"])
def test_list_reports_a_low_rate_limit_beside_the_page(
    tmp_path, monkeypatch, capsys, command
):
    if command == "issue":
        answers = (context(), search(hit(1)), reading(batch(node(1)), 400))
    else:
        pull = {
            **pull_request_node(1),
            "__typename": "PullRequest",
            "repository": {"id": REPOSITORY_ID},
        }
        answers = (context(), reading(search(pull), 400))
    source, _ = github(tmp_path, *answers)
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(cli, "configured_query_source", lambda *args, **kwargs: source)
    assert cli.main([command, "list", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["page"]["status"] == "fresh"
    (warning,) = document["page"]["diagnostics"]
    assert warning["code"] == "github-rate-limit-low"
    assert warning["severity"] == "warning"
    assert "400 of 5000 points remain until 2026-09-27T13:00:00Z" in warning["message"]
