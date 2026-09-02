from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    ValidationError,
    model_validator,
)

from .errors import DashpotError
from .models import (
    PublishedModel,
    translate_validation_error,
    validate_rfc3339_timestamp,
)


# The ValueError base is what the adapters' ``except ValueError`` translation
# sites match; the DashpotError base states the CLI contract if one escapes.
class IssueProfileError(DashpotError, ValueError):
    """A source record cannot satisfy the complete Issue profile."""


def _non_empty_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("must be a non-empty string")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value)


def _positive_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("must be a positive integer")
    return value


def _string_set(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("must be an array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError("item must be a non-empty string")
        items.append(item)
    if len(items) != len(set(items)):
        raise ValueError("must not contain duplicates")
    return tuple(sorted(items))


def _issue_state(value: object) -> str:
    if not isinstance(value, str) or value not in {"open", "closed"}:
        raise ValueError("must be 'open' or 'closed'")
    return value


def _optional_state_reason(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in {
        "completed",
        "duplicate",
        "not-planned",
        "reopened",
    }:
        raise ValueError(
            "must be null, 'completed', 'duplicate', 'not-planned', or 'reopened'"
        )
    return value


def _optional_timestamp(value: object) -> str | None:
    if value is None:
        return None
    return validate_rfc3339_timestamp(_non_empty_string(value))


def _https_url(value: object) -> str:
    text = _non_empty_string(value)
    url = urlsplit(text)
    if url.scheme != "https" or not url.netloc:
        raise ValueError("must be an absolute HTTPS URL")
    return text


def _repository_relative_path(value: object) -> str:
    text = _non_empty_string(value)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("must be a repository-relative POSIX path")
    return text


_NonEmptyString = Annotated[str, PlainValidator(_non_empty_string)]
_OptionalString = Annotated[str | None, PlainValidator(_optional_string)]
_PositiveInteger = Annotated[int, PlainValidator(_positive_integer)]
# The explicit serializer keeps `model_dump(mode="json")` from warning while
# it turns the canonical tuple back into the wire's JSON array.
_StringSet = Annotated[
    tuple[str, ...],
    PlainValidator(_string_set),
    PlainSerializer(list, return_type=list[str], when_used="json"),
]
_IssueState = Annotated[Literal["open", "closed"], PlainValidator(_issue_state)]
_OptionalStateReason = Annotated[
    Literal["completed", "duplicate", "not-planned", "reopened"] | None,
    PlainValidator(_optional_state_reason),
]
_OptionalTimestamp = Annotated[str | None, PlainValidator(_optional_timestamp)]
_HttpsUrl = Annotated[str, PlainValidator(_https_url)]
_RepositoryRelativePath = Annotated[str, PlainValidator(_repository_relative_path)]


class _ProfileModel(PublishedModel):
    """Validate one closed-key-set component of the Issue profile."""

    model_config = ConfigDict(extra="forbid")


class IssueRelationships(_ProfileModel):
    """Relate an Issue to its parent, sub-Issues, and blocking Issues."""

    parent: _OptionalString
    sub_issues: _StringSet
    blocked_by: _StringSet
    blocking: _StringSet


class GitHubIssueOrigin(_ProfileModel):
    """Record GitHub provenance with the durable repository identity."""

    kind: Literal["github"]
    repository_id: _NonEmptyString


class MarkdownIssueOrigin(_ProfileModel):
    """Record Local Issue Markdown provenance."""

    kind: Literal["markdown"]


class GitHubIssueLocation(_ProfileModel):
    """Locate an Issue at its current HTTPS GitHub URL."""

    kind: Literal["github"]
    url: _HttpsUrl


class MarkdownIssueLocation(_ProfileModel):
    """Locate a Local Issue at a repository-relative path and line."""

    kind: Literal["markdown"]
    path: _RepositoryRelativePath
    line: _PositiveInteger


IssueOrigin = Annotated[
    GitHubIssueOrigin | MarkdownIssueOrigin, Field(discriminator="kind")
]
IssueLocation = Annotated[
    GitHubIssueLocation | MarkdownIssueLocation, Field(discriminator="kind")
]


class IssueProfile(_ProfileModel):
    """Model one complete, source-neutral Issue snapshot."""

    id: _NonEmptyString
    project_id: _NonEmptyString
    number: _PositiveInteger
    reference: _NonEmptyString
    title: _NonEmptyString
    body: str
    state: _IssueState
    state_reason: _OptionalStateReason
    labels: _StringSet
    assignees: _StringSet
    author: _OptionalString
    relationships: IssueRelationships
    issue_type: _OptionalString
    milestone: _OptionalString
    created_at: _OptionalTimestamp
    updated_at: _OptionalTimestamp
    closed_at: _OptionalTimestamp
    origin: IssueOrigin
    location: IssueLocation

    @model_validator(mode="after")
    def _check_lifecycle_and_relationships(self) -> IssueProfile:
        """Enforce the cross-field state, lifecycle, and self-reference rules."""

        if self.state == "open" and self.state_reason not in {None, "reopened"}:
            raise ValueError("an open Issue cannot have a closed stateReason")
        if self.state == "closed" and self.state_reason == "reopened":
            raise ValueError("a closed Issue cannot have stateReason 'reopened'")
        related = (
            self.relationships.parent,
            *self.relationships.sub_issues,
            *self.relationships.blocked_by,
            *self.relationships.blocking,
        )
        if self.id in related:
            raise ValueError("an Issue cannot relate to itself")
        if self.state == "open" and self.closed_at is not None:
            raise ValueError("an open Issue must have closedAt null")
        return self


def conform_issue(value: Mapping[str, Any]) -> IssueProfile:
    """Validate and canonicalize one complete Issue snapshot."""

    if not isinstance(value, Mapping):
        raise IssueProfileError("issue must be an object")
    try:
        return IssueProfile.model_validate(dict(value))
    except ValidationError as exc:
        raise IssueProfileError(_translate(exc)) from exc


def issue_location(issue: IssueProfile) -> str:
    """The Issue Location as one actionable string: URL, or ``path:line``."""

    location = issue.location
    if location.kind == "github":
        return location.url
    return f"{location.path}:{location.line}"


def semantic_projection(issue: IssueProfile) -> dict[str, Any]:
    """Return the source-neutral facts used for semantic equivalence."""

    return issue.model_dump(mode="json", by_alias=True, exclude={"origin", "location"})


def semantically_equivalent(left: IssueProfile, right: IssueProfile) -> bool:
    """Compare complete Issues after excluding provenance and location."""

    return semantic_projection(left) == semantic_projection(right)


# The old hand validator's check order, which keeps the reported message
# stable for callers pinning error text.
_FIELD_ORDER = (
    "id",
    "projectId",
    "reference",
    "title",
    "number",
    "body",
    "state",
    "stateReason",
    "labels",
    "assignees",
    "author",
    "issueType",
    "milestone",
    "relationships",
    "createdAt",
    "updatedAt",
    "closedAt",
    "origin",
    "location",
)


def _translate(error: ValidationError) -> str:
    return translate_validation_error(
        error,
        root="issue",
        field_order=_FIELD_ORDER,
        union_tags=frozenset({"github", "markdown"}),
        union_message="kind must be 'github' or 'markdown'",
    )
