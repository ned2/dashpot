from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .model import AgentRun, Diagnostic, ProjectObservation


@dataclass(slots=True)
class IssueBindingResult:
    agent_runs: list[AgentRun]
    issue_runs: dict[str, list[str]]
    diagnostics: list[Diagnostic]


def bind_issue_runs(
    projects: Sequence[ProjectObservation],
    runs: Sequence[AgentRun],
) -> IssueBindingResult:
    """Validate Work Store Issue Bindings against the observed Issue universe."""
    issues_by_id: dict[str, list[dict]] = {}
    status_by_project: dict[str, str] = {}
    for project in projects:
        status_by_project[project.project_id] = project.status
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            issues_by_id.setdefault(issue["id"], []).append(issue)

    issue_runs: dict[str, list[str]] = {
        issue_id: [] for issue_id in issues_by_id
    }
    conflicting_ids = {
        issue_id
        for issue_id, matches in issues_by_id.items()
        if len(matches) > 1
    }
    diagnostics = [
        Diagnostic(
            f"issue:{issue_id}",
            "error",
            f"Issue Identity {issue_id} appears in more than one Project",
            "agent-issue-identity-conflict",
        )
        for issue_id in sorted(conflicting_ids)
    ]
    for run in runs:
        if not run.issue_id:
            continue
        matches = issues_by_id.get(run.issue_id, [])
        if len(matches) == 1:
            issue_runs[run.issue_id].append(run.id)
            if (
                run.issue_reference_hint
                and matches[0]["reference"] != run.issue_reference_hint
            ):
                diagnostics.append(
                    Diagnostic(
                        run.id,
                        "warning",
                        f"Issue reference hint {run.issue_reference_hint!r} "
                        "no longer matches the bound Issue's current Reference",
                        "agent-issue-hint-stale",
                    )
                )
        elif len(matches) > 1:
            continue
        elif any(status != "fresh" for status in status_by_project.values()):
            diagnostics.append(
                Diagnostic(
                    run.id,
                    "warning",
                    f"Cannot validate bound Issue Identity {run.issue_id} "
                    "while a Project Issue Source is not fresh",
                    "agent-issue-resolution-deferred",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    run.id,
                    "warning",
                    f"Bound Issue Identity {run.issue_id} was not observed",
                    "agent-issue-binding-unobserved",
                )
            )
    return IssueBindingResult(list(runs), issue_runs, diagnostics)
