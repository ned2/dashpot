from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable, Literal, Sequence

from .model import AgentRun, Diagnostic, ProjectObservation


@dataclass(frozen=True, slots=True)
class IssueBindingPromotion:
    agent_run_id: str
    issue_id: str
    hint_kind: Literal["reference", "branch"]
    expected_hint: str
    expected_observation_target: str
    expected_last_activity_at: str | None


@dataclass(slots=True)
class IssueBindingPlan:
    issue_runs: dict[str, list[str]]
    promotions: list[IssueBindingPromotion]
    diagnostics: list[Diagnostic]


@dataclass(slots=True)
class IssueBindingResult:
    agent_runs: list[AgentRun]
    issue_runs: dict[str, list[str]]
    diagnostics: list[Diagnostic]


BindingPromoter = Callable[
    [IssueBindingPromotion], tuple[bool, Diagnostic | None]
]


def plan_issue_bindings(
    projects: Sequence[ProjectObservation],
    runs: Sequence[AgentRun],
) -> IssueBindingPlan:
    """Plan Workspace-global Agent Run bindings without mutating observations."""
    issues_by_id: dict[str, list[dict]] = {}
    issues_by_project: dict[str, list[dict]] = {}
    status_by_project: dict[str, str] = {}
    for project in projects:
        status_by_project[project.project_id] = project.status
        if project.snapshot is None:
            continue
        issues_by_project[project.project_id] = project.snapshot.issues
        for issue in project.snapshot.issues:
            issues_by_id.setdefault(issue["id"], []).append(issue)

    issue_runs: dict[str, list[str]] = {
        issue_id: [] for issue_id in issues_by_id
    }
    promotions: list[IssueBindingPromotion] = []
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
        if run.issue_id:
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
            continue

        observed_status = status_by_project.get(run.observation_project_id)
        if observed_status != "fresh":
            diagnostics.append(
                Diagnostic(
                    run.id,
                    "warning",
                    "Cannot resolve Issue hint while the observed Project's "
                    "Issue Source is not fresh",
                    "agent-issue-resolution-deferred",
                )
            )
            continue
        observed_issues = issues_by_project.get(run.observation_project_id, [])
        hint_kind: Literal["reference", "branch"] | None = None
        expected_hint: str | None = None
        matches: list[dict] = []
        if run.issue_reference_hint:
            hint_kind = "reference"
            expected_hint = run.issue_reference_hint
            matches = [
                issue
                for issue in observed_issues
                if issue["reference"] == expected_hint
            ]
        elif run.branch:
            expected_hint = run.branch
            references = _references_from_branch(run.branch, observed_issues)
            if references is not None:
                hint_kind = "branch"
                matches = [
                    issue
                    for issue in observed_issues
                    if issue["reference"] in references
                ]
        if hint_kind is None or expected_hint is None:
            continue
        if len(matches) == 1:
            if matches[0]["id"] in conflicting_ids:
                continue
            if run.observation_target is None:
                diagnostics.append(
                    Diagnostic(
                        run.id,
                        "warning",
                        "Cannot persist Issue hint without a located Observation Target",
                        "agent-issue-resolution-deferred",
                    )
                )
                continue
            promotions.append(
                IssueBindingPromotion(
                    run.id,
                    matches[0]["id"],
                    hint_kind,
                    expected_hint,
                    run.observation_target,
                    run.last_activity_at,
                )
            )
        elif len(matches) > 1:
            diagnostics.append(
                Diagnostic(
                    run.id,
                    "warning",
                    f"Issue {hint_kind} hint {expected_hint!r} is ambiguous",
                    "agent-issue-hint-ambiguous",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    run.id,
                    "warning",
                    f"Issue {hint_kind} hint {expected_hint!r} did not match an Issue",
                    "agent-issue-hint-stale",
                )
            )
    return IssueBindingPlan(issue_runs, promotions, diagnostics)


def resolve_issue_bindings(
    projects: Sequence[ProjectObservation],
    runs: Sequence[AgentRun],
    promoter: BindingPromoter,
) -> IssueBindingResult:
    """Resolve and persist Workspace-global bindings as one operation."""
    return _complete_issue_bindings(
        plan_issue_bindings(projects, runs), runs, promoter
    )


def _complete_issue_bindings(
    plan: IssueBindingPlan,
    runs: Sequence[AgentRun],
    promoter: BindingPromoter,
) -> IssueBindingResult:
    """Persist planned bindings before exposing them as established relationships."""
    resolved_runs = list(runs)
    issue_runs = {
        issue_id: list(run_ids) for issue_id, run_ids in plan.issue_runs.items()
    }
    diagnostics = list(plan.diagnostics)
    run_indexes = {run.id: index for index, run in enumerate(resolved_runs)}
    for promotion in plan.promotions:
        try:
            succeeded, diagnostic = promoter(promotion)
        except (OSError, RuntimeError) as exc:
            succeeded = False
            diagnostic = Diagnostic(
                promotion.agent_run_id,
                "warning",
                f"Cannot persist Issue binding: {exc}",
                "agent-issue-binding-race",
            )
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if not succeeded:
            continue
        issue_runs[promotion.issue_id].append(promotion.agent_run_id)
        run_index = run_indexes[promotion.agent_run_id]
        resolved_runs[run_index] = replace(
            resolved_runs[run_index], issue_id=promotion.issue_id
        )
    return IssueBindingResult(resolved_runs, issue_runs, diagnostics)


def _references_from_branch(
    branch: str, issues: Sequence[dict]
) -> set[str] | None:
    if re.fullmatch(r"issue/[1-9][0-9]*", branch):
        suffix = f"#{branch.removeprefix('issue/')}"
        return {
            issue["reference"]
            for issue in issues
            if issue["reference"].endswith(suffix)
        }
    if branch.startswith("issue/") and branch.removeprefix("issue/"):
        return {branch.removeprefix("issue/")}
    return None
