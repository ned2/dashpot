from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from .issue_profile import IssueProfile
from .models import (
    FrozenMapping,
    LaxSequence,
    NonEmptyString,
    PublishedModel,
    Rfc3339Timestamp,
)

SourceStatus = Literal["fresh", "stale", "unavailable"]
RunState = Literal["running", "waiting", "unknown"]
TargetAvailability = Literal["available", "unavailable"]
# Git topology, as `git worktree list` reports it: the main working tree is
# listed first, followed by each linked working tree.
TargetRole = Literal["main", "linked"]


class ObservationModel(PublishedModel):
    """Freeze a published observation value on the shared model base."""


class Diagnostic(ObservationModel):
    source: str
    severity: Literal["info", "warning", "error"]
    message: str
    code: str | None = None


PullRequestState = Literal["open", "closed", "merged"]
PullRequestReviewDecision = Literal["approved", "changes-requested", "review-required"]
PullRequestCheckStatus = Literal["error", "expected", "failure", "pending", "success"]
PullRequestMergeability = Literal["mergeable", "conflicting"]


class LinkedPullRequest(ObservationModel):
    number: int
    url: str
    state: PullRequestState


class PullRequest(ObservationModel):
    """Publish one Pull Request of the Project's Git Repository."""

    id: NonEmptyString
    number: Annotated[int, Field(gt=0)]
    title: NonEmptyString
    url: NonEmptyString
    state: PullRequestState
    is_draft: bool
    head_branch: NonEmptyString
    base_branch: NonEmptyString
    author: NonEmptyString | None
    review_decision: PullRequestReviewDecision | None
    check_status: PullRequestCheckStatus | None
    mergeability: PullRequestMergeability | None
    created_at: Rfc3339Timestamp
    updated_at: Rfc3339Timestamp


class IssueActivity(ObservationModel):
    """Carry tracker engagement facts beside the Issue profile."""

    comment_count: int = 0
    linked_pull_requests: LaxSequence[LinkedPullRequest] = ()
    unlisted_pull_request_count: int = 0


class ObservationTarget(ObservationModel):
    path: str
    head: str
    branch: str | None
    detached: bool
    dirty: bool | None
    availability: TargetAvailability
    elapsed_ms: int
    diagnostics: LaxSequence[Diagnostic]
    role: TargetRole


class Branch(ObservationModel):
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
    # Commits reachable from this ref but not the Integration Branch; ``None``
    # when no comparison was available. A Remote-Tracking Branch carries the
    # result as of the Repository's last fetch.
    unintegrated_commits: int | None = None
    # Whether the Integration Branch already holds the content of those
    # unreachable commits, as after a squash merge; assessed only when there
    # are some, ``None`` when not assessed or Git could not answer.
    content_integrated: bool | None = None


class RepositoryStateInventory(ObservationModel):
    """Carry one Repository's observed state: Observation Targets and Branches."""

    targets: LaxSequence[ObservationTarget]
    diagnostics: LaxSequence[Diagnostic]
    # Every observed Branch of the repository, and when its Remote-Tracking
    # Branches were last fetched (``None`` when the repository never fetched).
    # Observation never fetches, so that age is the remote facts' freshness;
    # ``integration_ref`` is the ref their reachability facts compare with,
    # and ``branch_anchor`` the Repository Anchor whose refs answered, which
    # is the only one an explicit fetch may mutate.
    branches: LaxSequence[Branch] = ()
    fetched_at: str | None = None
    integration_ref: str | None = None
    branch_anchor: str | None = None


class AgentRun(ObservationModel):
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


class ProjectSnapshot(ObservationModel):
    project_id: str
    display_label: str
    repository_id: str
    collected_at: str
    issue_source_status: SourceStatus
    issue_source_attempted_at: str
    issue_source_last_good_at: str | None
    observation_targets: LaxSequence[ObservationTarget]
    issues: LaxSequence[IssueProfile]
    diagnostics: LaxSequence[Diagnostic]
    # Worktree topology is observed independently of the Issue Source, so its
    # freshness is reported separately. ``None`` timestamps mean the targets
    # were never attempted for this snapshot (single-shot collectors).
    target_status: SourceStatus = "fresh"
    target_attempted_at: str | None = None
    target_last_good_at: str | None = None
    # Tracker label colours (name -> "rrggbb") for the labels its Issues carry;
    # empty when the source has no palette.
    label_colors: FrozenMapping[str, str] = Field(default_factory=dict)
    issue_activity: FrozenMapping[str, IssueActivity] = Field(default_factory=dict)
    pull_request_status: SourceStatus = "unavailable"
    pull_request_attempted_at: str | None = None
    pull_request_last_good_at: str | None = None
    pull_requests: LaxSequence[PullRequest] = ()
    # Branches are observed with the worktree topology and share its
    # freshness; ``fetched_at`` is the last fetch of the Remote-Tracking
    # Branches, which observation reports rather than refreshes.
    # ``integration_ref`` is the Integration Branch their reachability facts
    # compare with, and ``branch_anchor`` the Repository Anchor whose refs
    # supplied them: the one an explicit fetch (``f``) mutates.
    branches: LaxSequence[Branch] = ()
    fetched_at: str | None = None
    integration_ref: str | None = None
    branch_anchor: str | None = None


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


class ProjectObservation(ObservationModel):
    project_id: str
    display_label: str
    repository_id: str
    workspaces: LaxSequence[str]
    anchors: LaxSequence[str]
    primary_anchor: str
    status: SourceStatus
    elapsed_ms: int
    snapshot: ProjectSnapshot | None
    diagnostics: LaxSequence[Diagnostic]


class WorkspaceSnapshot(ObservationModel):
    collected_at: str
    elapsed_ms: int
    projects: LaxSequence[ProjectObservation]
    agent_runs: LaxSequence[AgentRun] = ()
    issue_runs: FrozenMapping[str, LaxSequence[str]] = Field(default_factory=dict)
    diagnostics: LaxSequence[Diagnostic] = ()
