"""Pin observation documents and argument failures at the CLI seam."""

import json

import pytest

from dashpot import cli
from dashpot.queries import query_source
from test_source_queries import markdown, markdown_issue


def test_list_json_keys_and_cross_invocation_cursor(tmp_path, monkeypatch, capsys):
    source = markdown(tmp_path)
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        query_source, "configured_query_source", lambda *args, **kwargs: source
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
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        query_source, "configured_query_source", lambda *args, **kwargs: source
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
    monkeypatch.setattr(cli, "worktree_root", lambda current: tmp_path)
    monkeypatch.setattr(
        query_source, "configured_query_source", lambda *args, **kwargs: source
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
