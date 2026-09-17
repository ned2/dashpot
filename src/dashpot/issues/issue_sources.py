from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from typing_extensions import override

from ..core.issue_profile import IssueProfile, issue_location
from ..core.model import Diagnostic, IssueActivity, SourceStatus
from ..core.pydantic import FrozenDict
from .retaining_source import RetainingSource, SourceRefreshError


@dataclass(frozen=True, slots=True)
class IssueSourceObservation:
    """One adapter refresh outcome, constructed by the source it came from.

    Constructed from already-validated Issue Profiles rather than parsed, so
    it stays a frozen dataclass (ADR 0013); the mappings are frozen views so
    a consumer cannot corrupt the source's retained last-good state.
    """

    status: SourceStatus
    attempted_at: str
    last_good_at: str | None
    issues: tuple[IssueProfile, ...]
    diagnostics: tuple[Diagnostic, ...]
    # Presentation facts about the source's labels (name -> "rrggbb"). They
    # sit beside the Issue profile rather than inside it: a label's colour is
    # a property of the tracker, not of any one Issue.
    label_colors: Mapping[str, str] = field(default_factory=dict)
    # Comment counts and linked pull requests keyed by Issue Identity.
    issue_activity: Mapping[str, IssueActivity] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CollectedIssues:
    """One complete collection cycle, returned whole by an adapter's ``_collect``.

    Built from already-validated Issue Profiles, so it stays a frozen
    dataclass (ADR 0013). Returning the palette and activity beside the
    Issues keeps a cycle self-consistent and leaves the adapter stateless
    across cycles: a failed ``_collect`` has no instance stash to leak into
    the next observation.
    """

    issues: tuple[IssueProfile, ...]
    label_colors: Mapping[str, str] = field(default_factory=dict)
    issue_activity: Mapping[str, IssueActivity] = field(default_factory=dict)
    # What a complete cycle still wants a person to know (a rate limit
    # running low, say): warnings and information, never the failure a
    # raised ``IssueSourceRefreshError`` reports.
    diagnostics: tuple[Diagnostic, ...] = ()


_NUMBER_HINT = re.compile(r"#?([1-9][0-9]*)")
_GITHUB_ISSUE_URL = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)"
    r"/issues/(?P<number>[1-9][0-9]*)/?(?:\?\S*)?(?:#\S*)?"
)
_QUALIFIED_REFERENCE = re.compile(
    r"(?P<owner>[^/\s#]+)/(?P<repo>[^/\s#]+)#(?P<number>[1-9][0-9]*)"
)


@dataclass(frozen=True, slots=True)
class IssueHint:
    """One parsed Issue Hint: an Issue Reference when present, else a Number."""

    raw: str
    number: int | None
    reference: str | None

    def matches(self, issue: IssueProfile) -> bool:
        """Name the Issue exactly: by Reference when present, else by Number."""
        if self.reference is not None:
            return issue.reference == self.reference
        return self.number is not None and issue.number == self.number


def parse_issue_hint(hint: str) -> IssueHint:
    """Parse one Issue Hint: a Number, a Reference, or a pasted GitHub URL.

    The hint is stripped; matching stays exact and case-sensitive. A pasted
    GitHub Issue URL — the form ``issue_location`` prints — parses to the
    repository-qualified Reference it names, so it resolves only in the
    Project whose repository it belongs to.
    """
    text = hint.strip()
    number_match = _NUMBER_HINT.fullmatch(text)
    if number_match:
        return IssueHint(raw=text, number=int(number_match.group(1)), reference=None)
    url_match = _GITHUB_ISSUE_URL.fullmatch(text)
    if url_match:
        number = int(url_match["number"])
        return IssueHint(
            raw=text,
            number=number,
            reference=f"{url_match['owner']}/{url_match['repo']}#{number}",
        )
    qualified_match = _QUALIFIED_REFERENCE.fullmatch(text)
    if qualified_match:
        return IssueHint(
            raw=text, number=int(qualified_match["number"]), reference=text
        )
    return IssueHint(raw=text, number=None, reference=text or None)


class IssueSourceRefreshError(SourceRefreshError):
    """Diagnose one failed Issue Source refresh."""


class IssueSource(RetainingSource[CollectedIssues, IssueSourceObservation]):
    """Refresh complete Issue collections while retaining the last good value."""

    @property
    def code_prefix(self) -> str:
        """Prefix the shared diagnostic codes; defaults to the source name."""
        return self.name

    def find(self, hint: IssueHint) -> IssueProfile | None:
        """Resolve one Issue Hint to at most one Issue of a fresh collection.

        The default refreshes the complete collection and filters; an adapter
        overrides it when one Issue can be observed more cheaply. A miss is
        ``None``; a source that cannot answer freshly, or a detectable
        ambiguity, raises ``IssueSourceRefreshError``. ``refresh`` stays the
        only writer of the retained last-good state.
        """
        observation = self.refresh()
        if observation.status != "fresh":
            details = "; ".join(
                diagnostic.message for diagnostic in observation.diagnostics
            )
            code = (
                observation.diagnostics[0].code or f"{self.code_prefix}-unavailable"
                if observation.diagnostics
                else f"{self.code_prefix}-unavailable"
            )
            raise IssueSourceRefreshError(
                code,
                f"cannot resolve an Issue Hint while the Issue Source is "
                f"{observation.status}: {details or 'no diagnostics'}",
            )
        matches = [issue for issue in observation.issues if hint.matches(issue)]
        if len(matches) > 1:
            raise IssueSourceRefreshError(
                f"{self.code_prefix}-ambiguous-hint",
                f"Issue Reference {hint.raw!r} is ambiguous",
            )
        return matches[0] if matches else None

    @override
    def _check_collection_invariants(self, collected: CollectedIssues) -> None:
        """Refuse a collection that repeats an Issue identity or Issue Number.

        The Issue Profile contract makes both unique within a complete Project
        collection, so the invariant lives here rather than in each adapter.
        """
        issues_by_id: dict[str, IssueProfile] = {}
        issues_by_number: dict[int, IssueProfile] = {}
        for issue in collected.issues:
            previous = issues_by_id.get(issue.id)
            if previous is not None:
                raise IssueSourceRefreshError(
                    f"{self.code_prefix}-duplicate-identity",
                    f"{self.name} collected duplicate Issue identity {issue.id}, "
                    f"seen at {issue_location(previous)} and {issue_location(issue)}",
                )
            previous = issues_by_number.get(issue.number)
            if previous is not None:
                raise IssueSourceRefreshError(
                    f"{self.code_prefix}-duplicate-number",
                    f"{self.name} collected duplicate Issue Number #{issue.number}, "
                    f"seen at {issue_location(previous)} and {issue_location(issue)}",
                )
            issues_by_id[issue.id] = issue
            issues_by_number[issue.number] = issue

    @override
    def _snapshot(self, collected: CollectedIssues) -> CollectedIssues:
        """Freeze collection mappings before retaining or publishing them."""
        return replace(
            collected,
            label_colors=FrozenDict(collected.label_colors),
            issue_activity=FrozenDict(collected.issue_activity),
        )

    @override
    def _observation(
        self,
        collected: CollectedIssues | None,
        status: SourceStatus,
        attempted_at: str,
        diagnostics: tuple[Diagnostic, ...],
    ) -> IssueSourceObservation:
        value = collected or CollectedIssues(())
        return IssueSourceObservation(
            status=status,
            attempted_at=attempted_at,
            last_good_at=self._last_good_at,
            issues=value.issues,
            diagnostics=diagnostics,
            label_colors=FrozenDict(value.label_colors),
            issue_activity=FrozenDict(value.issue_activity),
        )
