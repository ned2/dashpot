"""Persist GitHub Issue snapshots as untrusted startup seeds."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, ValidationError, model_validator

from .issue_profile import GitHubIssueOrigin, IssueProfile
from .model import IssueActivity, LinkedPullRequest, PullRequestState
from .models import (
    FrozenMapping,
    LaxSequence,
    NonEmptyString,
    PublishedModel,
    Rfc3339Timestamp,
)
from .record_store import LockedRecordStore

GITHUB_ISSUE_SNAPSHOT_VERSION = 1
_SNAPSHOT_KEY = re.compile(r"[0-9a-f]{64}")
_LABEL_COLOR = re.compile(r"[0-9a-f]{6}")
_PositiveInteger = Annotated[int, Field(gt=0)]


class _SnapshotModel(PublishedModel):
    """Forbid fields outside one supported Snapshot Seed version."""

    model_config = ConfigDict(extra="forbid")


class GitHubPullRequestMarksRecord(_SnapshotModel):
    """Persist the settled Pull Request mark and its pending confirmation."""

    settled: Rfc3339Timestamp | None
    candidate: Rfc3339Timestamp | None

    @model_validator(mode="after")
    def _check_candidate(self) -> GitHubPullRequestMarksRecord:
        """Require a pending candidate to be later than the settled mark."""

        if (
            self.settled is not None
            and self.candidate is not None
            and _moment(self.candidate) <= _moment(self.settled)
        ):
            raise ValueError("candidate must be later than settled")
        return self


class GitHubLinkedPullRequestRecord(_SnapshotModel):
    """Persist one Linked Pull Request beside an Issue."""

    number: _PositiveInteger
    url: NonEmptyString
    state: PullRequestState

    @classmethod
    def of(cls, pull_request: LinkedPullRequest) -> GitHubLinkedPullRequestRecord:
        """Build the persisted form of a Linked Pull Request."""

        return cls(
            number=pull_request.number,
            url=pull_request.url,
            state=pull_request.state,
        )

    def linked_pull_request(self) -> LinkedPullRequest:
        """Build the published Linked Pull Request from persisted fields."""

        return LinkedPullRequest(number=self.number, url=self.url, state=self.state)


class GitHubIssueActivityRecord(_SnapshotModel):
    """Persist the tracker engagement facts beside one Issue."""

    comment_count: Annotated[int, Field(ge=0)]
    linked_pull_requests: LaxSequence[GitHubLinkedPullRequestRecord]
    unlisted_pull_request_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _check_linked_pull_requests(self) -> GitHubIssueActivityRecord:
        """Require the published lowest-numbered Linked Pull Request prefix."""

        numbers = tuple(item.number for item in self.linked_pull_requests)
        if len(numbers) > 20:
            raise ValueError("linkedPullRequests must contain at most 20 items")
        if len(numbers) != len(set(numbers)):
            raise ValueError("linkedPullRequests must not repeat a Pull Request")
        if numbers != tuple(sorted(numbers)):
            raise ValueError("linkedPullRequests must be ordered by number")
        return self

    @classmethod
    def of(cls, activity: IssueActivity) -> GitHubIssueActivityRecord:
        """Build the persisted form of Issue Activity."""

        return cls(
            comment_count=activity.comment_count,
            linked_pull_requests=[
                GitHubLinkedPullRequestRecord.of(pull_request)
                for pull_request in activity.linked_pull_requests
            ],
            unlisted_pull_request_count=activity.unlisted_pull_request_count,
        )

    def issue_activity(self) -> IssueActivity:
        """Build the published Issue Activity from persisted fields."""

        return IssueActivity(
            comment_count=self.comment_count,
            linked_pull_requests=[
                pull_request.linked_pull_request()
                for pull_request in self.linked_pull_requests
            ],
            unlisted_pull_request_count=self.unlisted_pull_request_count,
        )


class GitHubObservedIssueRecord(_SnapshotModel):
    """Persist one complete Issue and the source-private facts beside it."""

    issue: IssueProfile
    updated_at: Rfc3339Timestamp
    activity: GitHubIssueActivityRecord
    linked_pull_request_numbers: LaxSequence[_PositiveInteger]
    label_colors: FrozenMapping[str, str]

    @model_validator(mode="after")
    def _check_internal_agreement(self) -> GitHubObservedIssueRecord:
        """Require the private facts to agree with the embedded Issue Profile."""

        if self.issue.updated_at != self.updated_at:
            raise ValueError("updatedAt must equal issue.updatedAt")
        numbers = tuple(self.linked_pull_request_numbers)
        if len(numbers) != len(set(numbers)):
            raise ValueError("linkedPullRequestNumbers must not contain duplicates")
        listed = {
            pull_request.number for pull_request in self.activity.linked_pull_requests
        }
        if not listed.issubset(numbers):
            raise ValueError(
                "activity.linkedPullRequests must occur in linkedPullRequestNumbers"
            )
        if not set(self.label_colors).issubset(self.issue.labels):
            raise ValueError("labelColors must name labels of the Issue")
        if any(
            not _LABEL_COLOR.fullmatch(color) for color in self.label_colors.values()
        ):
            raise ValueError("labelColors values must be lowercase rrggbb strings")
        return self


class GitHubIssueSnapshotRecord(_SnapshotModel):
    """Validate one complete GitHub Issue Snapshot Seed."""

    version: Literal[1]
    project_id: NonEmptyString
    repository_id: NonEmptyString
    issues: LaxSequence[GitHubObservedIssueRecord]
    high_water: Rfc3339Timestamp
    pull_request_marks: GitHubPullRequestMarksRecord

    @model_validator(mode="after")
    def _check_collection(self) -> GitHubIssueSnapshotRecord:
        """Require one Project and Repository with unique Issues and Numbers."""

        identities: set[str] = set()
        numbers: set[int] = set()
        for entry in self.issues:
            issue = entry.issue
            if issue.project_id != self.project_id:
                raise ValueError("every Issue must belong to projectId")
            origin = issue.origin
            if not isinstance(origin, GitHubIssueOrigin):
                raise ValueError("every Issue must have a GitHub origin")
            if origin.repository_id != self.repository_id:
                raise ValueError("every Issue must belong to repositoryId")
            if issue.id in identities:
                raise ValueError(f"duplicate Issue identity {issue.id}")
            if issue.number in numbers:
                raise ValueError(f"duplicate Issue Number #{issue.number}")
            identities.add(issue.id)
            numbers.add(issue.number)
        return self


class GitHubIssueSnapshotStore:
    """Read and atomically replace Snapshot Seeds for one Worktree."""

    def __init__(self, root: Path) -> None:
        self._records = LockedRecordStore(
            root / ".dashpot" / "state" / "github-issues",
            _SNAPSHOT_KEY,
            "GitHub Issue Snapshot Seed key is invalid",
        )

    def path(self, repository_id: str) -> Path:
        """Name the record by a safe digest of the opaque Repository Identity."""

        return self._records.record_path(_snapshot_key(repository_id))

    def load(
        self, *, repository_id: str, project_id: str
    ) -> GitHubIssueSnapshotRecord | None:
        """Load one valid identity-matched Snapshot Seed, else ignore it."""

        path = self.path(repository_id)
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
            record = GitHubIssueSnapshotRecord.model_validate(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            return None
        if record.repository_id != repository_id or record.project_id != project_id:
            return None
        return record

    def replace(self, record: GitHubIssueSnapshotRecord) -> Path:
        """Replace one Repository's Snapshot Seed atomically under its lock."""

        key = _snapshot_key(record.repository_id)
        with self._records.locked(key):
            self._records.replace(key, record.model_dump(by_alias=True, mode="json"))
        return self._records.record_path(key)


def _snapshot_key(repository_id: str) -> str:
    return hashlib.sha256(repository_id.encode("utf-8")).hexdigest()


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
