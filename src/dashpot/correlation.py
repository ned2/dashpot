from __future__ import annotations

import re
from typing import Any

from .model import AgentRun


def correlate_issues(
    issues: list[dict[str, Any]], runs: list[AgentRun]
) -> dict[str, list[str]]:
    by_reference = {issue["reference"]: issue["id"] for issue in issues}
    issue_runs = {issue["id"]: [] for issue in issues}
    for run in runs:
        if not run.declared_issue_reference:
            run.declared_issue_reference = issue_reference_from_branch(
                run.branch, issues
            )
        issue_id = by_reference.get(run.declared_issue_reference or "")
        if issue_id:
            issue_runs[issue_id].append(run.id)
    return issue_runs


def issue_reference_from_branch(
    branch: str | None, issues: list[dict[str, Any]]
) -> str | None:
    if not branch:
        return None
    if re.fullmatch(r"issue/[1-9][0-9]*", branch):
        suffix = f"#{branch.removeprefix('issue/')}"
        matches = [issue["reference"] for issue in issues if issue["reference"].endswith(suffix)]
    elif branch.startswith("issue/") and branch.removeprefix("issue/"):
        reference = branch.removeprefix("issue/")
        matches = [issue["reference"] for issue in issues if issue["reference"] == reference]
    else:
        return None
    return matches[0] if len(matches) == 1 else None
