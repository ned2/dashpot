from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Literal

from pydantic import BaseModel

from .issue_profile import IssueProfile

SourceStatus = Literal["fresh", "stale", "unavailable"]
RunState = Literal["running", "waiting", "unknown"]
TargetAvailability = Literal["available", "unavailable"]
# Git topology, as `git worktree list` reports it: the main working tree is
# listed first, followed by each linked working tree.
TargetRole = Literal["main", "linked"]


@dataclass(slots=True)
class Diagnostic:
    source: str
    severity: Literal["info", "warning", "error"]
    message: str
    code: str | None = None


PullRequestState = Literal["open", "closed", "merged"]


@dataclass(slots=True)
class LinkedPullRequest:
    number: int
    url: str
    state: PullRequestState


@dataclass(slots=True)
class IssueActivity:
    """Tracker engagement facts that sit beside the Issue profile.

    They are GitHub-shaped rather than source-neutral, so they travel with
    the snapshot keyed by Issue Identity instead of inside each Issue.
    """

    comment_count: int = 0
    linked_pull_requests: list[LinkedPullRequest] = field(default_factory=list)


@dataclass(slots=True)
class ObservationTarget:
    path: str
    head: str
    branch: str | None
    detached: bool
    dirty: bool | None
    availability: TargetAvailability
    elapsed_ms: int
    diagnostics: list[Diagnostic]
    role: TargetRole


@dataclass(slots=True)
class Branch:
    """One Git ref under ``refs/heads`` or ``refs/remotes``, as observed.

    Identity is the full ``refname``: ``refs/heads/x`` and
    ``refs/remotes/origin/x`` are two refs about one branch name, and the
    read model joins them. ``remote`` names the remote of a Remote-Tracking
    Branch rather than flagging it, so a fork with ``origin`` and ``upstream``
    is representable; it is ``None`` for a local branch. The upstream facts
    are only ever set on a local branch.
    """

    refname: str
    name: str
    remote: str | None
    head: str
    committed_at: str
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    upstream_gone: bool = False
    checked_out_at: str | None = None
    # Commits reachable from this local Branch but not the Integration Branch;
    # ``None`` when no comparison was available or for a Remote-Tracking Branch.
    unintegrated_commits: int | None = None


@dataclass(slots=True)
class ObservationTargetInventory:
    targets: list[ObservationTarget]
    diagnostics: list[Diagnostic]
    # Every observed Branch of the repository, and when its Remote-Tracking
    # Branches were last fetched (``None`` when the repository never fetched).
    # Dashpot never fetches, so that age is the remote facts' freshness;
    # ``integration_ref`` is the ref their reachability facts compare with.
    branches: list[Branch] = field(default_factory=list)
    fetched_at: str | None = None
    integration_ref: str | None = None


@dataclass(slots=True)
class AgentRun:
    id: str
    harness: str
    process_or_session: str
    state: RunState
    observation_target: str | None
    observation_project_id: str
    branch: str | None
    issue_id: str | None
    issue_reference_hint: str | None
    working_directory: str | None = None
    # When the run was last observed doing something, when its running turn
    # began, and when the run itself began. They answer different questions
    # and only the first is an activity observation.
    last_activity_at: str | None = None
    turn_started_at: str | None = None
    started_at: str | None = None


@dataclass(slots=True)
class ProjectSnapshot:
    project_id: str
    display_label: str
    repository_id: str
    collected_at: str
    issue_source_status: SourceStatus
    issue_source_attempted_at: str
    issue_source_last_good_at: str | None
    observation_targets: list[ObservationTarget]
    issues: list[IssueProfile]
    diagnostics: list[Diagnostic]
    # Worktree topology is observed independently of the Issue Source, so its
    # freshness is reported separately. ``None`` timestamps mean the targets
    # were never attempted for this snapshot (single-shot collectors).
    target_status: SourceStatus = "fresh"
    target_attempted_at: str | None = None
    target_last_good_at: str | None = None
    # Tracker label colours (name -> "rrggbb") for the labels its Issues carry;
    # empty when the source has no palette.
    label_colors: dict[str, str] = field(default_factory=dict)
    issue_activity: dict[str, IssueActivity] = field(default_factory=dict)
    # Branches are observed with the worktree topology and share its
    # freshness; ``fetched_at`` is the last fetch of the Remote-Tracking
    # Branches, which Dashpot reports rather than refreshes. ``integration_ref``
    # is the Integration Branch their reachability facts compare with.
    branches: list[Branch] = field(default_factory=list)
    fetched_at: str | None = None
    integration_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryAnchor:
    path: str


@dataclass(frozen=True, slots=True)
class Workspace:
    name: str
    anchors: tuple[RepositoryAnchor, ...]


@dataclass(frozen=True, slots=True)
class ResolvedProject:
    project_id: str
    display_label: str
    repository_id: str
    workspaces: tuple[str, ...]
    anchors: tuple[str, ...]
    primary_anchor: str


@dataclass(slots=True)
class ProjectObservation:
    project_id: str
    display_label: str
    repository_id: str
    workspaces: list[str]
    anchors: list[str]
    primary_anchor: str
    status: SourceStatus
    elapsed_ms: int
    snapshot: ProjectSnapshot | None
    diagnostics: list[Diagnostic]


@dataclass(slots=True)
class WorkspaceSnapshot:
    collected_at: str
    elapsed_ms: int
    projects: list[ProjectObservation]
    agent_runs: list[AgentRun] = field(default_factory=list)
    issue_runs: dict[str, list[str]] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def to_jsonable(value: object) -> object:
    # TEMPORARY (ADR 0013 step 3b): dump a model with today's wire shape —
    # camelCase keys and explicit nulls, never the dataclass omit-None rule.
    # Deleted with the rest of to_jsonable at step 8.
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return {
            camel_case(item.name): to_jsonable(getattr(value, item.name))
            for item in fields(value)
            if getattr(value, item.name) is not None
        }
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


def camel_case(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)
