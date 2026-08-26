from __future__ import annotations

from dashpot.correlation import correlate_issues, issue_reference_from_branch
from dashpot.model import AgentRun


def issue(issue_id: str, reference: str) -> dict:
    return {"id": issue_id, "reference": reference}


def run(reference: str | None = None, branch: str | None = None) -> AgentRun:
    return AgentRun(
        id="codex-session:1",
        harness="codex",
        process_or_session="1 hook",
        state="running",
        repository_root="/repo",
        worktree="/repo",
        branch=branch,
        declared_issue_reference=reference,
    )


def test_explicit_issue_reference_correlates_without_mutating_issue() -> None:
    declared = issue("I_7", "example/project#7")
    observed = run("example/project#7")

    issue_runs = correlate_issues([declared], [observed])

    assert issue_runs == {"I_7": ["codex-session:1"]}
    assert declared == {"id": "I_7", "reference": "example/project#7"}


def test_github_issue_branch_infers_unambiguous_reference() -> None:
    issues = [issue("I_7", "example/project#7")]

    assert issue_reference_from_branch("issue/7", issues) == "example/project#7"


def test_numeric_issue_branch_does_not_guess_across_projects() -> None:
    issues = [
        issue("I_7", "example/one#7"),
        issue("I_other_7", "example/two#7"),
    ]

    assert issue_reference_from_branch("issue/7", issues) is None


def test_local_issue_branch_matches_the_full_reference() -> None:
    issues = [issue("I_local", "build-observer")]

    assert issue_reference_from_branch("issue/build-observer", issues) == "build-observer"
