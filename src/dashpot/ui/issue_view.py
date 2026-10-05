"""Full-screen, read-only rendering of one Issue.

This screen is the one reading surface for an Issue: the table row is the
at-a-glance summary and everything else is read here. It is source-neutral:
everything shown comes from the complete Issue profile plus the snapshot facts
that travel beside it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, override

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Footer, Markdown, Static

from ..core.ages import relative_age
from ..core.issue_profile import IssueProfile, issue_location
from ..core.model import ProjectObservation
from ..issues.ordering import is_priority_label, issue_activity, issue_priority
from ..observation.issue_list import IssueListRow, unobserved_auxiliary
from .detail_fields import DetailFields, DetailItem
from .issue_cells import (
    cells_match,
    issue_state_chip,
    issue_state_kind,
    label_chips,
    label_colors,
)

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
        self.rendering: IssueRendering | None = None

    @override
    def compose(self) -> ComposeResult:
        rendering = self.render_context()
        self.rendering = rendering
        with (
            Vertical(id="issue-view", classes=rendering.state_class),
            Horizontal(id="issue-view-panes"),
        ):
            with VerticalScroll(id="issue-view-body", can_focus=True):
                # Where the Issue lives sits left and when it was opened
                # right, on the one line that heads the body.
                with Horizontal(id="issue-view-heading"):
                    yield Static(
                        rendering.location, id="issue-view-location", markup=False
                    )
                    yield Static(
                        rendering.byline,
                        id="issue-view-subtitle",
                        markup=False,
                    )
                # Both are composed and one is shown, so a body that comes
                # or goes later changes only which.
                markdown = Markdown(rendering.body, id="issue-view-markdown")
                empty = Static(EMPTY_BODY_MESSAGE, id="issue-view-empty", markup=False)
                markdown.display = bool(rendering.body)
                empty.display = not rendering.body
                yield markdown
                yield empty
            yield DetailFields(
                *rendering.metadata,
                id="issue-view-metadata",
                classes="issue-view-metadata",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, self.on_theme_changed)
        self.dress_panes()
        self.query_one("#issue-view-body").focus()

    def render_context(self) -> IssueRendering:
        """What the view renders of its current projection, in the current theme."""
        return issue_rendering(
            self.context, now=self.now, dark=self.app.current_theme.dark
        )

    def dress_panes(self) -> None:
        """Give the panes the titles, focusability and stacking compose leaves unset."""
        self.query_one("#issue-view-body").border_title = Content(
            selection_title(self.context)
        )
        self.query_one("#issue-view-metadata").border_title = "DETAILS"
        self.query_one("#issue-view-metadata").can_focus = True
        self.apply_layout(self.size.width)

    def on_theme_changed(self, _theme: Theme) -> None:
        """Re-render the chips, whose colours follow the theme's brightness."""
        self.update_panes()

    def on_resize(self, event: events.Resize) -> None:
        self.apply_layout(event.size.width)

    def apply_layout(self, width: int) -> None:
        self.query_one("#issue-view").set_class(width < STACK_BELOW_WIDTH, "-stacked")

    @property
    def stacked(self) -> bool:
        return self.query_one("#issue-view").has_class("-stacked")

    def show(self, context: IssueListRow) -> None:
        """Show a newer projection of the open Issue in place.

        A projection differs from the last in facts the view never renders,
        such as when its Project was observed, so the panes are updated
        rather than rebuilt: whatever renders the same is left untouched, and
        each pane keeps the place a person scrolled it to.
        """
        self.context = context
        self.issue = context.issue
        self.update_panes()

    def update_panes(self) -> None:
        """Bring each pane up to the current projection, changing only what differs."""
        shown = self.rendering
        # Until the view is composed, compose renders the newest projection
        # itself; once it is detached there is nothing left to update.
        if shown is None or not (self.is_mounted and self.is_attached):
            return
        rendering = self.render_context()
        self.rendering = rendering
        if rendering.state_class != shown.state_class:
            view = self.query_one("#issue-view")
            view.remove_class(shown.state_class)
            view.add_class(rendering.state_class)
        if rendering.title != shown.title:
            self.query_one("#issue-view-body").border_title = Content(rendering.title)
        if rendering.location != shown.location:
            self.query_one("#issue-view-location", Static).update(rendering.location)
        if rendering.byline != shown.byline:
            self.query_one("#issue-view-subtitle", Static).update(rendering.byline)
        if rendering.body != shown.body:
            self.update_body(rendering.body)
        if not details_match(rendering.metadata, shown.metadata):
            self.query_one("#issue-view-metadata", DetailFields).update(
                *rendering.metadata, keep_scroll=True
            )

    def update_body(self, body: str) -> None:
        """Render a changed body, or say the Issue has none."""
        markdown = self.query_one("#issue-view-markdown", Markdown)
        markdown.update(body)
        markdown.display = bool(body)
        self.query_one("#issue-view-empty").display = not body

    def action_close(self) -> None:
        self.dismiss(None)


@dataclass(frozen=True, slots=True, eq=False)
class IssueRendering:
    """Everything the Issue view renders of one projection, and nothing else.

    The view compares one rendering with the next field by field, so a
    projection that differs only in facts the view never shows leaves it as
    a person left it. Its metadata is compared with ``details_match``, since
    Rich's own equality overlooks a chip's colour.
    """

    state_class: str
    title: str
    location: str
    byline: str
    body: str
    metadata: tuple[DetailItem, ...]


def issue_rendering(
    context: IssueListRow, *, now: datetime | None = None, dark: bool = True
) -> IssueRendering:
    """Render one projection of an Issue as the Issue view shows it."""
    issue = context.issue
    return IssueRendering(
        state_class=issue_state_class(issue),
        title=selection_title(context),
        location=issue_location(issue),
        byline=issue_byline(issue, now=now),
        # A blank body renders as no body at all, whatever its whitespace.
        body=issue.body if issue.body.strip() else "",
        metadata=issue_metadata_items(context, now=now, dark=dark),
    )


def details_match(left: Sequence[DetailItem], right: Sequence[DetailItem]) -> bool:
    """Whether two runs of detail fields render alike, styles included."""
    return len(left) == len(right) and all(
        mine.label == theirs.label
        and mine.kind == theirs.kind
        and cells_match(mine.value, theirs.value)
        for mine, theirs in zip(left, right, strict=True)
    )


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

    activity = (
        (context.auxiliary.activity if context.auxiliary else None)
        if context.queried
        else issue_activity(issue, context.project)
    )
    if activity is None:
        availability = unobserved_auxiliary(context)
        items.append(DetailItem(availability, "Comments"))
        items.append(DetailItem(availability, "Linked Pull Requests"))
    else:
        items.append(DetailItem(str(activity.comment_count), "Comments"))
        items.append(DetailItem("Pull requests", kind="section"))
        if activity.linked_pull_requests:
            items.extend(
                DetailItem(f"#{pull.number} {pull.state} {pull.url}", kind="list")
                for pull in activity.linked_pull_requests
            )
        else:
            items.append(DetailItem("-", kind="list"))
        if activity.unlisted_pull_request_count:
            items.append(
                DetailItem(
                    f"and {activity.unlisted_pull_request_count} more", kind="list"
                )
            )

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
                    f"{label}: {_describe_related(issue_id, context.project, context.related_issues)}",
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
        items.append(DetailItem(f"{run.id} ({run.activity}, {location})", kind="list"))
    return tuple(items)


def _timestamp(value: str | None, now: datetime) -> str:
    if value is None:
        return "-"
    age = relative_age(value, now)
    day = value[:10]
    return f"{day} ({age})" if age else day


def _describe_related(
    issue_id: str, project: ProjectObservation, related: tuple[IssueProfile, ...] = ()
) -> str:
    """Name a related Issue by number, title and state, else by its identity.

    Only an Issue Dashpot holds, related or in the same Project, has a number,
    title and state to show.
    """
    candidates = (
        *related,
        *(project.snapshot.issues if project.snapshot is not None else ()),
    )
    for candidate in candidates:
        if candidate.id == issue_id:
            return f"#{candidate.number} {candidate.title} ({candidate.state})"
    return issue_id
