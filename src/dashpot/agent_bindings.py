from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .model import AgentRun, Diagnostic, Issue, ProjectObservation


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
    issues_by_id: dict[str, list[Issue]] = {}
    status_by_project: dict[str, str] = {}
    for project in projects:
        status_by_project[project.project_id] = project.status
        if project.snapshot is None:
            continue
        for issue in project.snapshot.issues:
            issues_by_id.setdefault(issue["id"], []).append(issue)

    issue_runs: dict[str, list[str]] = {issue_id: [] for issue_id in issues_by_id}
    conflicting_ids = {
        issue_id for issue_id, matches in issues_by_id.items() if len(matches) > 1
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
        elif _resolution_deferred(run, status_by_project):
            diagnostics.append(
                Diagnostic(
                    run.id,
                    "warning",
                    f"Cannot validate bound Issue Identity {run.issue_id} "
                    "while the Project's Issue Source is not fresh",
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


def _resolution_deferred(run: AgentRun, status_by_project: dict[str, str]) -> bool:
    """Whether the run's own Project cannot yet vouch for its Issue Binding.

    An Issue Binding names an Issue in the Project the run is observed under,
    so only that Project's Issue Source needs to be fresh before its absence
    means anything. A run observed under no known Project falls back to the
    freshness of every source.
    """
    status = status_by_project.get(run.observation_project_id)
    if status is None:
        return any(status != "fresh" for status in status_by_project.values())
    return status != "fresh"
