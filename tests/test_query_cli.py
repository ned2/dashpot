"""Pin observation documents and argument failures at the CLI seam."""

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from dashpot import cli, composition
from test_github_issues import REPOSITORY_ID
from test_github_pull_requests import pull_request_node
from test_query_pages import (
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
from test_runtime_spans import executable


@pytest.fixture(autouse=True)
def gh_record(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Fail any test here that starts a ``gh`` process, real or not.

    The CLI's Query Source comes from ``composition``, which reads
    ``configured_query_source`` through its own name, so a test that patches
    any other name gets the configured Query Source instead, and a GitHub
    Query Source would reach the real ``gh`` (#331). A ``gh`` first on
    ``PATH`` appends each call to the record this yields and fails. A test
    that means to start it reads the record and removes it.
    """
    directory = tmp_path_factory.mktemp("gh-guard")
    record = directory / "calls"
    executable(
        directory,
        "gh",
        "import sys\n"
        f"with open({str(record)!r}, 'a') as calls:\n"
        "    calls.write(' '.join(sys.argv[1:]) + '\\n')\n"
        "sys.exit(1)",
    )
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    yield record
    assert not record.exists(), f"a test started gh: {record.read_text()}"


def test_a_github_source_the_cli_builds_itself_reaches_the_gh_guard(
    tmp_path, monkeypatch, capsys, gh_record
):
    github(tmp_path)  # Only for the GitHub configuration it writes.
    monkeypatch.setattr(composition, "worktree_root", lambda current: tmp_path)
    assert cli.main(["issue", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["page"]["status"] == "unavailable"
    # Unpatched, the CLI's own Query Source starts gh, which the guard records.
    assert gh_record.read_text().startswith("api graphql")
    gh_record.unlink()


def test_list_json_keys_and_cross_invocation_cursor(tmp_path, monkeypatch, capsys):
    source = markdown(tmp_path)
    monkeypatch.setattr(composition, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        composition, "configured_query_source", lambda *args, **kwargs: source
    )
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
    monkeypatch.setattr(composition, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        composition, "configured_query_source", lambda *args, **kwargs: source
    )
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
    monkeypatch.setattr(composition, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        composition, "configured_query_source", lambda *args, **kwargs: source
    )
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
@pytest.mark.usefixtures("local_clock_ten_hours_ahead")
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
    monkeypatch.setattr(composition, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        composition, "configured_query_source", lambda *args, **kwargs: source
    )
    assert cli.main([command, "list", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["page"]["status"] == "fresh"
    (warning,) = document["page"]["diagnostics"]
    assert warning["code"] == "github-rate-limit-low"
    assert warning["severity"] == "warning"
    # A --json document has no dashboard to name the clock, so the offset does.
    assert "400 of 5000 points remain until 23:00:00 +10:00;" in warning["message"]
