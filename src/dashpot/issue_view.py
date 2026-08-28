"""Full-screen, read-only rendering of one Issue.

The compact selection pane stays the at-a-glance surface; this screen is the
canonical reading surface. It is source-neutral: everything shown comes from
the complete Issue profile plus the snapshot facts that travel beside it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Markdown, Static
from typing_extensions import override

from .detail_fields import DetailFields, DetailItem
from .issue_list import IssueListRow
from .issue_table import (
    is_priority_label,
    issue_activity,
    issue_priority,
    issue_state_kind,
    label_chips,
    label_colors,
    relative_age,
)
from .model import Issue, ProjectObservation

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
        if context.issue is None:
            raise ValueError("an Issue view needs an Issue row")
        self.context = context
        self.issue: Issue = context.issue
        self.now = now

    @override
    def compose(self) -> ComposeResult:
        issue = self.issue
        with Vertical(id="issue-view"), Horizontal(id="issue-view-panes"):
            with VerticalScroll(id="issue-view-body", can_focus=True):
                with Vertical(id="issue-view-heading"):
                    yield Static(issue["title"], id="issue-view-title", markup=False)
                    yield Static(
                        issue_view_subtitle(issue, self.context.project, now=self.now),
                        id="issue-view-subtitle",
                        markup=False,
                    )
                if issue["body"].strip():
                    yield Markdown(issue["body"], id="issue-view-markdown")
                else:
                    yield Static(
                        EMPTY_BODY_MESSAGE,
                        id="issue-view-empty",
                        markup=False,
                    )
            yield DetailFields(
                *issue_metadata_items(self.context, now=self.now),
                id="issue-view-metadata",
                classes="issue-view-metadata",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#issue-view-body").border_title = "ISSUE"
        self.query_one("#issue-view-metadata").border_title = "DETAILS"
        self.query_one("#issue-view-metadata").can_focus = True
        self.query_one("#issue-view-body").focus()
        self.apply_layout(self.size.width)

    def on_resize(self, event: events.Resize) -> None:
        self.apply_layout(event.size.width)

    def apply_layout(self, width: int) -> None:
        self.query_one("#issue-view").set_class(width < STACK_BELOW_WIDTH, "-stacked")

    @property
    def stacked(self) -> bool:
        return self.query_one("#issue-view").has_class("-stacked")

    def action_close(self) -> None:
        self.dismiss(None)


def issue_view_subtitle(
    issue: Issue, project: ProjectObservation, *, now: datetime | None = None
) -> str:
    """``ned2/dashpot#12 · Dashpot · open · opened 3d ago by ned2``."""
    current = now or datetime.now(UTC)
    parts = [issue["reference"], project.display_label, issue_state_label(issue)]
    opened = ["opened"]
    age = relative_age(issue["createdAt"], current)
    if age:
        opened.append(age)
    if issue["author"]:
        opened.append(f"by {issue['author']}")
    parts.append(" ".join(opened))
    return " · ".join(parts)


def issue_state_label(issue: Issue) -> str:
    kind = issue_state_kind(issue)
    if kind == "open":
        return "reopened" if issue["stateReason"] == "reopened" else "open"
    if kind == "completed":
        return "closed as completed"
    return f"closed as {kind}"


def issue_metadata_items(
    context: IssueListRow, *, now: datetime | None = None
) -> tuple[DetailItem, ...]:
    """Every applicable profile fact for the metadata pane.

    Scalar facts that are positively absent read as ``-`` so the pane keeps
    one shape across Issues; empty collections show a single ``-`` entry.
    """
    issue = context.issue
    if issue is None:
        raise ValueError("Issue metadata needs an Issue row")
    current = now or datetime.now(UTC)
    labels = [label for label in issue["labels"] if not is_priority_label(label)]
    items: list[DetailItem] = [
        DetailItem(issue_state_label(issue), "State"),
        DetailItem(issue["author"] or "-", "Author"),
        DetailItem(", ".join(issue["assignees"]) or "unassigned", "Assignees"),
        DetailItem(label_chips(labels, label_colors(context.project)), "Labels"),
        DetailItem(issue_priority(issue), "Priority"),
        DetailItem(issue["issueType"] or "-", "Type"),
        DetailItem(issue["milestone"] or "-", "Milestone"),
        DetailItem(_timestamp(issue["createdAt"], current), "Created"),
        DetailItem(_timestamp(issue["updatedAt"], current), "Updated"),
        DetailItem(_timestamp(issue["closedAt"], current), "Closed"),
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

    relationships = issue["relationships"]
    items.append(DetailItem("Relationships", kind="section"))
    related = [
        ("Parent", [relationships["parent"]] if relationships["parent"] else []),
        ("Sub-issues", relationships["subIssues"]),
        ("Blocked by", relationships["blockedBy"]),
        ("Blocking", relationships["blocking"]),
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
            if candidate["id"] == issue_id:
                return f"#{candidate['number']} {candidate['title']}"
    return issue_id
