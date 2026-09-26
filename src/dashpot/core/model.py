"""Publish the observation read model: the Workspace Snapshot and its parts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator
from typing_extensions import TypeIs

from .issue_profile import IssueProfile
from .pydantic import (
    FrozenMapping,
    LaxSequence,
    NonEmptyString,
    PublishedModel,
    Rfc3339Timestamp,
)

SourceStatus = Literal["fresh", "stale", "unavailable"]
RunState = Literal["running", "waiting", "unknown"]
# What a person reads about a session: its turn state, or that its process is
# gone while its Agent Run is still held (an Orphaned Agent Run). The two are
# different facts, so the published ``RunState`` stays turn activity alone.
SessionActivity = Literal["running", "waiting", "unknown", "orphaned"]
# The supported harnesses and how each is named to a person; every harness
# value in the code, the persisted records, and the published model is one of
# these, and observation reads the labels here without importing ``sessions``.
Harness = Literal["codex", "claude-code"]
HARNESS_DISPLAY: dict[Harness, str] = {"codex": "Codex", "claude-code": "Claude Code"}


def is_harness(value: object) -> TypeIs[Harness]:
    """Tell whether a value names a supported harness."""
    return value in HARNESS_DISPLAY


TargetAvailability = Literal["available", "unavailable"]
# Git topology, as `git worktree list` reports it: the main working tree is
# listed first, followed by each linked working tree.
TargetRole = Literal["main", "linked"]
# How one ref stands against the Integration Branch: its commits reachable,
# its content held though its commits are not, work retained, or no answer.
IntegrationState = Literal[
    "integrated", "content-integrated", "unintegrated", "unknown"
]


def integration_state(
    unintegrated_commits: int | None, content_integrated: bool | None
) -> IntegrationState:
    """Classify one ref's integration facts; missing evidence is unknown."""
    if unintegrated_commits is None:
        return "unknown"
    if unintegrated_commits == 0:
        return "integrated"
    if content_integrated:
        return "content-integrated"
    return "unintegrated"


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


class OpenBlocker(ObservationModel):
    """An Issue that blocks another and is still open.

    ``reference`` and ``number`` are unknown for a blocker a Local Issue
    declares by an identity its collection does not hold; such a blocker
    still counts as open, so an Issue is never shown Ready on missing
    evidence.
    """

    id: NonEmptyString
    reference: NonEmptyString | None = None
    number: Annotated[int, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def validate_name(self) -> OpenBlocker:
        """Refuse a blocker whose Reference and number are not known together."""
        if (self.reference is None) != (self.number is None):
            raise ValueError("An Open Blocker's Reference and number go together")
        return self


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
    harness: Harness
    process_or_session: str
    # Live cursor continuity does not extend the headless snapshot contract.
    session_id: str | None = Field(default=None, exclude=True)
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
    # An Orphaned Agent Run: its session's recorded process is gone although
    # no graceful end was observed. Its ``state`` is then ``unknown`` and its
    # last activity is when the session was last seen. ``host_restarted`` says
    # whether the host has booted since that process started, when known.
    orphaned: bool = False
    host_restarted: bool | None = None

    @property
    def activity(self) -> SessionActivity:
        """What a person reads about this run: orphaned, or its turn state."""
        return "orphaned" if self.orphaned else self.state


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
