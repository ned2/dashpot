"""Publish scoped Query Pages independently of complete Workspace exports."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from ..core.errors import DashpotError
from ..core.issue_profile import IssueProfile
from ..core.model import (
    Diagnostic,
    IssueActivity,
    ObservationModel,
    OpenBlocker,
    PullRequest,
    SourceStatus,
)
from ..core.pydantic import (
    FrozenMapping,
    LaxSequence,
    NonEmptyString,
    Rfc3339Timestamp,
)
from ..issues.lifecycle import Lifecycle

ResourceKind = Literal["issues", "pull-requests"]
PAGED_KINDS: tuple[ResourceKind, ...] = ("issues", "pull-requests")

# The Query Sources the shipped app consults, one per concurrent consumer:
# each key runs against its own source instance.
QUERY_SOURCE_KEYS: tuple[str, ...] = (*PAGED_KINDS, "identities")


class QueryRequest(ObservationModel):
    model_config = ConfigDict(extra="forbid")

    kind: ResourceKind = "issues"
    query: str = ""
    state: Lifecycle = "open"
    ordering: str = "provider-default"
    page_size: Annotated[int, Field(ge=1, le=100)] = 50
    cursor: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> QueryRequest:
        """Refuse Ready for Pull Requests, which have no blockers to wait on.

        ``ready`` lists open Issues with no open blocker.
        """
        if self.state == "ready" and self.kind != "issues":
            raise ValueError("Only an Issue query can ask for Ready Issues")
        return self


class SourceContext(ObservationModel):
    model_config = ConfigDict(extra="forbid")

    project_id: NonEmptyString
    repository_id: NonEmptyString
    source: Literal["github", "local-markdown"]
    location: NonEmptyString
    principal: str | None = None
    revision: str | None = None
    configuration: str | None = None


class ObservationFacts(ObservationModel):
    model_config = ConfigDict(extra="forbid")

    status: SourceStatus
    attempted_at: Rfc3339Timestamp
    last_good_at: Rfc3339Timestamp | None
    diagnostics: LaxSequence[Diagnostic] = ()


class AuxiliaryObservation(ObservationFacts):
    activity: IssueActivity | None = None
    label_colors: FrozenMapping[str, str] | None = None
    # The Issue's open blockers in the order its source lists them; ``None``
    # when they were not observed, which is not the same as none.
    open_blockers: LaxSequence[OpenBlocker] | None = None


class QueryPage(ObservationFacts):
    context: SourceContext
    request: QueryRequest
    effective_ordering: str
    issues: LaxSequence[IssueProfile] = ()
    pull_requests: LaxSequence[PullRequest] = ()
    auxiliary: FrozenMapping[str, AuxiliaryObservation] = Field(default_factory=dict)
    returned_count: Annotated[int, Field(ge=0)]
    matched_count: Annotated[int, Field(ge=0)] | None
    next_cursor: NonEmptyString | None
    continuation: Literal["more", "end", "provider-limit", "unavailable"]
    result_limit: Annotated[int, Field(gt=0)] | None

    @model_validator(mode="after")
    def validate_coverage(self) -> QueryPage:
        """Reject inconsistent page coverage and resource records."""
        rows = self.issues if self.request.kind == "issues" else self.pull_requests
        if self.pull_requests if self.request.kind == "issues" else self.issues:
            raise ValueError("Query Page contains the wrong resource kind")
        if len(rows) != self.returned_count or len(rows) > self.request.page_size:
            raise ValueError("Query Page returned count does not match its records")
        if len({row.id for row in rows}) != len(rows) or len(
            {row.number for row in rows}
        ) != len(rows):
            raise ValueError("Query Page contains duplicate identities or numbers")
        if (self.continuation == "more") != (self.next_cursor is not None):
            raise ValueError(
                "Only a Query Page with more results has a continuation token"
            )
        if self.status == "fresh" and (
            self.matched_count is None or self.continuation == "unavailable"
        ):
            raise ValueError("A fresh Query Page must report matching coverage")
        if self.status == "unavailable" and (rows or self.last_good_at is not None):
            raise ValueError("An unavailable Query Page cannot publish records")
        if any(issue.project_id != self.context.project_id for issue in self.issues):
            raise ValueError("Query Page contains an Issue from another Project")
        return self


class ProjectTotals(ObservationFacts):
    context: SourceContext
    kind: ResourceKind
    open_count: Annotated[int, Field(ge=0)] | None
    closed_count: Annotated[int, Field(ge=0)] | None


@dataclass(frozen=True, slots=True)
class PageObservation:
    """A Query Page and the Project Totals observed by the same request.

    The totals keep their own status: they count the whole Project whatever
    the page's query, so a search the source refuses can still count.
    """

    page: QueryPage
    totals: ProjectTotals


class ResolvedIssue(ObservationFacts):
    context: SourceContext
    issue_id: NonEmptyString
    outcome: Literal["resolved", "outside-repository", "not-resolved", "unavailable"]
    issue: IssueProfile | None = None
    auxiliary: AuxiliaryObservation | None = None
    reference: str | None = None
    observed_repository_id: str | None = None

    @model_validator(mode="after")
    def validate_membership(self) -> ResolvedIssue:
        """Keep outside-Repository evidence separate from Project membership."""
        if self.issue is not None and (
            self.issue.id != self.issue_id
            or self.issue.project_id != self.context.project_id
        ):
            raise ValueError(
                "Resolved Issue does not match the requested identity and Project"
            )
        if self.outcome == "resolved" and self.issue is None:
            raise ValueError("Resolved outcome requires a complete Issue Profile")
        if (
            self.outcome in {"outside-repository", "not-resolved"}
            and self.issue is not None
        ):
            raise ValueError("Non-resolution cannot publish a Project Issue Profile")
        return self


class SourceEnumeration(ObservationFacts):
    context: SourceContext
    kind: ResourceKind
    issues: LaxSequence[IssueProfile] = ()
    pull_requests: LaxSequence[PullRequest] = ()
    auxiliary: FrozenMapping[str, AuxiliaryObservation] = Field(default_factory=dict)


class QuerySource(Protocol):
    @property
    def search_prompt(self) -> str: ...

    def supports_sort(self, request: QueryRequest, column: str) -> bool: ...

    def source_diagnostics(self) -> tuple[Diagnostic, ...]:
        """What the source reports about itself rather than about one observation."""
        ...

    @property
    def context(self) -> SourceContext: ...

    def query_page(self, request: QueryRequest) -> PageObservation: ...

    def resolve_identities(
        self, identities: Sequence[str]
    ) -> tuple[ResolvedIssue, ...]: ...

    def enumerate_source(self, kind: ResourceKind) -> SourceEnumeration: ...


class InvalidContinuation(DashpotError, ValueError):
    """Refuse a malformed, mismatched or expired continuation."""


class Continuation(ObservationModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    fingerprint: NonEmptyString
    offset: Annotated[int, Field(gt=0, le=1000000000)]
    provider_cursor: Annotated[str, Field(max_length=4096)] | None = None
    trail: Annotated[LaxSequence[str], Field(max_length=1000)] = ()


def context_fingerprint(context: SourceContext, request: QueryRequest) -> str:
    """Bind continuation to non-secret source evidence and the complete request."""
    payload = [
        context.model_dump(mode="json"),
        request.model_dump(mode="json", exclude={"cursor"}),
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def encode_continuation(value: Continuation) -> str:
    """Encode a portable continuation without credentials or persistent state."""
    return (
        base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip("=")
    )


def decode_continuation(token: str) -> Continuation:
    """Validate an opaque continuation before attempting source observation."""
    try:
        if len(token) > 262144:
            raise ValueError("oversized token")
        raw = base64.b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        )
        return Continuation.model_validate(json.loads(raw))
    except (ValueError, binascii.Error) as exc:
        raise InvalidContinuation(
            "Invalid continuation; restart from page one"
        ) from exc


def verify_continuation(
    value: Continuation | None, context: SourceContext, request: QueryRequest
) -> None:
    """Compare continuation only after its source context has been observed."""
    if value is not None and value.fingerprint != context_fingerprint(context, request):
        raise InvalidContinuation(
            "Continuation context changed or expired; restart from page one"
        )


def cursor_digest(cursor: str) -> str:
    """Bound forward cursor history independently of provider cursor length."""
    return hashlib.sha256(cursor.encode()).hexdigest()
