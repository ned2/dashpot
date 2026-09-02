"""Full-screen, read-only rendering of one Issue.

This screen is the one reading surface for an Issue: the table row is the
at-a-glance summary and everything else is read here. It is source-neutral:
everything shown comes from the complete Issue profile plus the snapshot facts
that travel beside it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Footer, Markdown, Static
from typing_extensions import override

from .detail_fields import DetailFields, DetailItem
from .issue_list import IssueListRow
from .issue_profile import IssueProfile, issue_location
from .issue_table import (
    is_priority_label,
    issue_activity,
    issue_priority,
    issue_state_chip,
    issue_state_kind,
    label_chips,
    label_colors,
    relative_age,
)
from .model import ProjectObservation

EMPTY_BODY_MESSAGE = "This Issue has no description."

# Below this width the metadata pane stacks under the body instead of
# squeezing it into an unreadable column.
STACK_BELOW_WIDTH = 90


class IssueScreen(Screen[None]):
    """Read one Issue: rendered Markdown body beside its metadata."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Back"),
    ]

    def __init__(self, context: IssueListRow, *, now: datetime | None = None) -> None:
        super().__init__()
        self.context = context
        self.issue: IssueProfile = context.issue
        self.now = now

    @override
    def compose(self) -> ComposeResult:
        issue = self.issue
        with (
            Vertical(id="issue-view", classes=issue_state_class(issue)),
            Horizontal(id="issue-view-panes"),
        ):
            with VerticalScroll(id="issue-view-body", can_focus=True):
                # Where the Issue lives sits left and when it was opened
                # right, on the one line that heads the body.
                with Horizontal(id="issue-view-heading"):
                    yield Static(
                        issue_location(issue), id="issue-view-location", markup=False
                    )
                    yield Static(
                        issue_byline(issue, now=self.now),
                        id="issue-view-subtitle",
                        markup=False,
                    )
                if issue.body.strip():
                    yield Markdown(issue.body, id="issue-view-markdown")
                else:
                    yield Static(
                        EMPTY_BODY_MESSAGE,
                        id="issue-view-empty",
                        markup=False,
                    )
            yield DetailFields(
                *issue_metadata_items(
                    self.context, now=self.now, dark=self.app.current_theme.dark
                ),
                id="issue-view-metadata",
                classes="issue-view-metadata",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#issue-view-body").border_title = Content(
            selection_title(self.context)
        )
        self.query_one("#issue-view-metadata").border_title = "DETAILS"
        self.query_one("#issue-view-metadata").can_focus = True
        self.query_one("#issue-view-body").focus()
        self.app.theme_changed_signal.subscribe(self, self.on_theme_changed)
        self.apply_layout(self.size.width)

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render the chips, whose colours follow the theme's brightness."""
        self.query_one("#issue-view-metadata", DetailFields).update(
            *issue_metadata_items(
                self.context, now=self.now, dark=self.app.current_theme.dark
            )
        )

    def on_resize(self, event: events.Resize) -> None:
        self.apply_layout(event.size.width)

    def apply_layout(self, width: int) -> None:
        self.query_one("#issue-view").set_class(width < STACK_BELOW_WIDTH, "-stacked")

    @property
    def stacked(self) -> bool:
        return self.query_one("#issue-view").has_class("-stacked")

    def action_close(self) -> None:
        self.dismiss(None)


def issue_byline(issue: IssueProfile, *, now: datetime | None = None) -> str:
    """Frame an Issue as ``opened 3d ago by ned2``."""
    current = now or datetime.now(UTC)
    parts = ["opened"]
    age = relative_age(issue.created_at, current)
    if age:
        parts.append(age)
    if issue.author:
        parts.append(f"by {issue.author}")
    return " ".join(parts)


def selection_title(context: IssueListRow) -> str:
    """Title the selected Issue with its compact human label."""
    return f"#{context.issue.number}: {context.issue.title}"


def issue_state_class(issue: IssueProfile) -> str:
    """The stylesheet class that colours the view by the Issue's state."""
    return f"-issue-{issue_state_kind(issue)}"


def issue_state_label(issue: IssueProfile) -> str:
    kind = issue_state_kind(issue)
    if kind == "open":
        return "reopened" if issue.state_reason == "reopened" else "open"
    if kind == "completed":
        return "closed as completed"
    return f"closed as {kind}"


def issue_metadata_items(
    context: IssueListRow, *, now: datetime | None = None, dark: bool = True
) -> tuple[DetailItem, ...]:
    """Every applicable profile fact for the metadata pane.

    Scalar facts that are positively absent read as ``-`` so the pane keeps
    one shape across Issues; empty collections show a single ``-`` entry.
    """
    issue = context.issue
    current = now or datetime.now(UTC)
    labels = [label for label in issue.labels if not is_priority_label(label)]
    items: list[DetailItem] = [
        DetailItem(
            issue_state_chip(issue, issue_state_label(issue), dark=dark), "State"
        ),
        DetailItem(issue.author or "-", "Author"),
        DetailItem(", ".join(issue.assignees) or "unassigned", "Assignees"),
        DetailItem(label_chips(labels, label_colors(context.project)), "Labels"),
        DetailItem(issue_priority(issue) or "-", "Priority"),
        DetailItem(issue.issue_type or "-", "Type"),
        DetailItem(issue.milestone or "-", "Milestone"),
        DetailItem(_timestamp(issue.created_at, current), "Created"),
        DetailItem(_timestamp(issue.updated_at, current), "Updated"),
        DetailItem(_timestamp(issue.closed_at, current), "Closed"),
    ]

    activity = issue_activity(issue, context.project)
    items.append(DetailItem(str(activity.comment_count), "Comments"))
    items.append(DetailItem("Pull requests", kind="section"))
    if activity.linked_pull_requests:
        items.extend(
            DetailItem(f"#{pull.number} {pull.state} {pull.url}", kind="list")
            for pull in activity.linked_pull_requests
        )
    else:
        items.append(DetailItem("-", kind="list"))

    relationships = issue.relationships
    items.append(DetailItem("Relationships", kind="section"))
    related: list[tuple[str, tuple[str, ...]]] = [
        ("Parent", (relationships.parent,) if relationships.parent else ()),
        ("Sub-issues", relationships.sub_issues),
        ("Blocked by", relationships.blocked_by),
        ("Blocking", relationships.blocking),
    ]
    if not any(ids for _label, ids in related):
        items.append(DetailItem("-", kind="list"))
    for label, ids in related:
        for issue_id in ids:
            items.append(
                DetailItem(
                    f"{label}: {_describe_related(issue_id, context.project)}",
                    kind="list",
                )
            )

    items.append(DetailItem("Agent sessions", kind="section"))
    if not context.observed_runs:
        items.append(DetailItem("-", kind="list"))
    for run in context.observed_runs:
        location = (
            run.branch
            or run.observation_target
            or run.working_directory
            or "unknown location"
        )
        items.append(DetailItem(f"{run.id} ({run.state}, {location})", kind="list"))
    return tuple(items)


def _timestamp(value: str | None, now: datetime) -> str:
    if value is None:
        return "-"
    age = relative_age(value, now)
    day = value[:10]
    return f"{day} ({age})" if age else day


def _describe_related(issue_id: str, project: ProjectObservation) -> str:
    """Name a related Issue by number and title when it is in the same
    Project, otherwise fall back to its opaque identity."""
    if project.snapshot is not None:
        for candidate in project.snapshot.issues:
            if candidate.id == issue_id:
                return f"#{candidate.number} {candidate.title}"
    return issue_id
