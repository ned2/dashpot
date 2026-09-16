"""Share selected GitHub response shapes and GraphQL field selections."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .model import PullRequestState
from .models import LaxSequence, NonEmptyString, WireModel


class Identity(WireModel):
    id: NonEmptyString


class Repository(Identity):
    name_with_owner: NonEmptyString


class PageInfo(WireModel):
    has_next_page: bool
    end_cursor: str | None


class SearchConnection(WireModel):
    issue_count: int = Field(ge=0)
    nodes: LaxSequence[dict[str, Any]]
    page_info: PageInfo


PULL_REQUEST_STATES: dict[str, PullRequestState] = {
    "OPEN": "open",
    "CLOSED": "closed",
    "MERGED": "merged",
}

PULL_REQUEST_FIELDS = (
    "id",
    "number",
    "title",
    "url",
    "state",
    "isDraft",
    "headRefName",
    "baseRefName",
    "author { login }",
    "reviewDecision",
    "statusCheckRollup { state }",
    "mergeable",
    "createdAt",
    "updatedAt",
)

ISSUE_NODE_FIELDS = """
          id
          number
          url
          title
          body
          state
          stateReason
          labels(first: 100) {
            nodes { name color }
            pageInfo { hasNextPage endCursor }
          }
          assignees(first: 100) {
            nodes { login }
            pageInfo { hasNextPage endCursor }
          }
          author { login }
          parent { id }
          subIssues(first: 100) {
            nodes { id }
            pageInfo { hasNextPage endCursor }
          }
          blockedBy(first: 100) {
            nodes { id }
            pageInfo { hasNextPage endCursor }
          }
          blocking(first: 100) {
            nodes { id }
            pageInfo { hasNextPage endCursor }
          }
          issueType { name }
          milestone { title }
          comments { totalCount }
          closedByPullRequestsReferences(first: 20, includeClosedPrs: true) {
            totalCount
            nodes { number url state }
            pageInfo { hasNextPage endCursor }
          }
          createdAt
          updatedAt
          closedAt
          repository { id nameWithOwner }
""".strip("\n")
