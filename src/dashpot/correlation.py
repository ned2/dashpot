from __future__ import annotations

import re

from .model import AgentRun, WorkItem


def correlate(work_items: list[WorkItem], runs: list[AgentRun]) -> None:
    by_key = {item.key: item for item in work_items}
    for item in work_items:
        item.observed_runs.clear()
    for run in runs:
        if not run.declared_work_key:
            run.declared_work_key = explicit_key_from_branch(run.branch, work_items)
        if run.declared_work_key and run.declared_work_key in by_key:
            by_key[run.declared_work_key].observed_runs.append(run.id)


def explicit_key_from_branch(branch: str | None, work_items: list[WorkItem]) -> str | None:
    if not branch:
        return None
    if branch.startswith("task/") and branch.removeprefix("task/"):
        source = "tasks-md"
        suffix = f":{branch.removeprefix('task/')}"
    elif re.fullmatch(r"issue/[1-9][0-9]*", branch):
        source = "github-issues"
        suffix = f"#{branch.removeprefix('issue/')}"
    else:
        return None
    matches = [item.key for item in work_items if item.source == source and item.key.endswith(suffix)]
    return matches[0] if len(matches) == 1 else None
