from __future__ import annotations

import re

from .model import AgentRun, Task


def correlate(tasks: list[Task], runs: list[AgentRun]) -> None:
    by_key = {task.key: task for task in tasks}
    for task in tasks:
        task.observed_runs.clear()
    for run in runs:
        if not run.declared_work_key:
            run.declared_work_key = explicit_key_from_branch(run.branch, tasks)
        if run.declared_work_key and run.declared_work_key in by_key:
            by_key[run.declared_work_key].observed_runs.append(run.id)


def explicit_key_from_branch(branch: str | None, tasks: list[Task]) -> str | None:
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
    matches = [
        task.key
        for task in tasks
        if task.source == source and task.key.endswith(suffix)
    ]
    return matches[0] if len(matches) == 1 else None
