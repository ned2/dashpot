"""The Runtime screen's Events tab: this dashboard's recent Runtime Events, one per row.

It reads the dashboard's in-memory buffer, every level whatever the level in
force, and shows it newest last, filtered by level, by kind and to failures.
The table follows the newest event until a person moves its cursor or
scrolls up, and ``End`` follows again. The selected event's every field is
shown beside it, its stored UTC time among them, so a row can be matched to
its line in the Event Log.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import ClassVar, Literal, Protocol, cast, get_args, override

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.scrollbar import ScrollTo, ScrollUp
from textual.widgets import Checkbox, DataTable, Select, Static

from ..core.event_log import EventLog
from ..core.event_log_files import event_fields, event_instant
from ..core.runtime_events import (
    AgentSessionChanged,
    CommandAttributes,
    DiagnosticChanged,
    EventLevel,
    EventLogWriteFailed,
    EventName,
    GitHubRequestAttributes,
    LevelChanged,
    ObservationAttributes,
    ProcessEnd,
    ProcessFacts,
    QueryAttributes,
    RateLimitPauseChanged,
    RefreshAttributes,
    RuntimeEvent,
    SpanEnded,
    SpanName,
    SubagentsAcknowledged,
    UnattendedPauseChanged,
    is_recorded,
)
from ..core.timestamps import observed_instant
from ..repository.cleanup import counted
from .detail_fields import DetailFields, DetailItem
from .marked_widgets import MarkedCheckbox
from .runtime_stats_view import clock_text, duration_text

# Which buffered events to show: all of them, what the level in force
# writes to the Event Log, or only what ``standard`` writes.
EventShow = Literal["all", "recorded", "standard"]
SHOW_OPTIONS: tuple[tuple[str, EventShow], ...] = (
    ("All buffered", "all"),
    ("Recorded at current level", "recorded"),
    ("Standard only", "standard"),
)
ALL_KINDS = "all"
# A fixed list rather than the kinds in the buffer, so the options do not
# shift while the list is open. A span is its own kind by its span name.
EVENT_KINDS: tuple[str, ...] = tuple(
    sorted(
        {str(kind) for kind in (*get_args(SpanName), *get_args(EventName))} - {"span"}
    )
)
KIND_OPTIONS: tuple[tuple[str, str], ...] = (
    ("All kinds", ALL_KINDS),
    *((kind, kind) for kind in EVENT_KINDS),
)
# The summary's length varies most, so it comes last and the fixed columns
# stay in view.
COLUMNS = ("time", "level", "kind", "project", "outcome", "duration", "summary")
# Below this width the detail pane stacks under the table, as the Issue
# view's metadata does.
STACK_BELOW_WIDTH = 90
FOLLOWING = "following"
PAUSED = "paused · End follows"


@dataclass(frozen=True, slots=True)
class EventFilter:
    """Which buffered Runtime Events the Events tab shows."""

    show: EventShow = "all"
    kind: str = ALL_KINDS
    errors_only: bool = False


def event_kind(event: RuntimeEvent) -> str:
    """The event's name, or its span name for a span."""
    body = event.body
    return body.span_name if isinstance(body, SpanEnded) else body.name


def is_failure(event: RuntimeEvent) -> bool:
    """Whether the event says work failed: a failed span or a dropped write."""
    body = event.body
    if isinstance(body, SpanEnded):
        return body.status == "ERROR"
    return isinstance(body, EventLogWriteFailed)


def accepts(event_filter: EventFilter, event: RuntimeEvent, level: EventLevel) -> bool:
    """Whether ``event_filter`` shows ``event`` while ``level`` is in force."""
    if event_filter.show == "recorded" and not is_recorded(event.level, level):
        return False
    if event_filter.show == "standard" and event.level != "standard":
        return False
    if event_filter.kind != ALL_KINDS and event_kind(event) != event_filter.kind:
        return False
    return not event_filter.errors_only or is_failure(event)


def event_project_id(event: RuntimeEvent) -> str | None:
    """The Project the event names, as its process or its observation key does."""
    attributes = event.body.attributes if isinstance(event.body, SpanEnded) else None
    if isinstance(attributes, ObservationAttributes) and attributes.project_id:
        return attributes.project_id
    return event.process.project_id


def local_time(event: RuntimeEvent) -> str:
    """When the event happened, or its span started, on the local clock to the millisecond."""
    instant = event_instant(event).astimezone()
    return f"{instant:%H:%M:%S}.{instant.microsecond // 1000:03d}"


def _words(*parts: object) -> str:
    return " ".join(str(part) for part in parts if part is not None and part != "")


def span_summary(span: SpanEnded) -> str:
    """What one span's work was, by its kind's attributes."""
    attributes = span.attributes
    if isinstance(attributes, CommandAttributes):
        return _words(attributes.program, attributes.subcommand)
    if isinstance(attributes, GitHubRequestAttributes):
        cost = None if attributes.cost is None else f"· cost {attributes.cost}"
        left = (
            None if attributes.remaining is None else f"· {attributes.remaining:,} left"
        )
        return _words(attributes.api, attributes.operation, cost, left)
    if isinstance(attributes, RefreshAttributes):
        return f"trigger {attributes.trigger}"
    if isinstance(attributes, ObservationAttributes):
        return attributes.kind
    if isinstance(attributes, QueryAttributes):
        return attributes.key
    return ""


def event_summary(event: RuntimeEvent) -> str:
    """A short phrase for what the event says, or its fields where none is written."""
    body = event.body
    if isinstance(body, SpanEnded):
        return span_summary(body)
    if isinstance(body, AgentSessionChanged):
        session = event.process.session_id
        return _words(
            body.change, event.process.harness, None if session is None else session[:8]
        )
    if isinstance(body, SubagentsAcknowledged):
        session = event.process.session_id
        return _words(
            body.outcome,
            "despite",
            f"{counted(len(body.agents), 'sub-agent')} of",
            event.process.harness,
            None if session is None else session[:8],
        )
    if isinstance(body, DiagnosticChanged):
        code = body.code if body.source is None else f"{body.source}:{body.code}"
        return _words(body.change, code, f"({body.severity})")
    if isinstance(body, RateLimitPauseChanged):
        until = event_instant_text(body.until)
        return _words(body.change, body.limit, f"until {until}")
    if isinstance(body, UnattendedPauseChanged):
        return _words(body.change, body.signal)
    if isinstance(body, LevelChanged):
        return f"{body.previous} → {body.current}"
    if isinstance(body, ProcessFacts):
        return _words(body.version, body.install_kind, f"pid {body.pid}")
    if isinstance(body, ProcessEnd):
        return f"exit {body.exit_code}"
    if isinstance(body, EventLogWriteFailed):
        return body.error_type
    fields = body.model_dump(mode="json", by_alias=True, exclude_none=True)
    fields.pop("event.name", None)
    return " ".join(f"{name}={value}" for name, value in flattened(fields))


def event_instant_text(stamp: str) -> str:
    """A stored UTC stamp on the local clock, to the second."""
    return clock_text(observed_instant(stamp))


def event_outcome(event: RuntimeEvent) -> Text:
    """How the event's work ended: a span's status, exit code or key outcome."""
    body = event.body
    if isinstance(body, EventLogWriteFailed):
        return Text("dropped", style="bold red")
    if not isinstance(body, SpanEnded):
        return Text("")
    if body.status == "ERROR":
        return Text(_words("ERROR", body.error_type), style="bold red")
    attributes = body.attributes
    if isinstance(attributes, CommandAttributes) and attributes.exit_code:
        return Text(f"exit {attributes.exit_code}")
    if isinstance(attributes, ObservationAttributes | QueryAttributes):
        return Text(attributes.outcome or "OK")
    return Text("OK")


def event_duration(event: RuntimeEvent) -> str:
    """How long a span or a process took, blank for an instant."""
    body = event.body
    if isinstance(body, SpanEnded | ProcessEnd):
        return duration_text(body.duration_seconds)
    return ""


def event_row(
    event: RuntimeEvent, project_label: Callable[[str], str]
) -> list[str | Text]:
    """The table's cells for one event, in the order of ``COLUMNS``."""
    project = event_project_id(event)
    return [
        local_time(event),
        "std" if event.level == "standard" else "full",
        event_kind(event),
        "" if project is None else project_label(project),
        event_outcome(event),
        event_duration(event),
        event_summary(event),
    ]


def flattened(fields: Mapping[str, object]) -> Iterator[tuple[str, str]]:
    """Every field and its value as text, a nested group's fields in its place."""
    for name, value in fields.items():
        if isinstance(value, Mapping):
            yield from flattened(value)
        elif isinstance(value, bool):
            yield name, "true" if value else "false"
        else:
            yield name, str(value)


def event_detail(event: RuntimeEvent) -> tuple[DetailItem, ...]:
    """Every field the event's line holds, under its on-disk name, its UTC time first."""
    return tuple(
        DetailItem(value, label=name) for name, value in flattened(event_fields(event))
    )


class EventTable(DataTable[str | Text]):
    """The buffered events newest last, following the newest until a person looks back.

    Rows are keyed by each event's number in the buffer, so the table adds
    only events it has not seen and lets go of those the buffer let go of.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("end", "follow", "Follow Newest"),
    ]

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id, cursor_type="row", zebra_stripes=True)
        self.following = True
        self.events: dict[str, RuntimeEvent] = {}
        # The number of the next event the table has not been offered.
        self.next_number: int | None = None

    @override
    def on_mount(self) -> None:
        for column in COLUMNS:
            self.add_column(column, key=column)

    def sync(
        self,
        first: int,
        buffered: tuple[RuntimeEvent, ...],
        *,
        accept: Callable[[RuntimeEvent], bool],
        project_label: Callable[[str], str],
        rebuild: bool,
    ) -> None:
        """Show the buffer as it stands: ``buffered`` from event number ``first``."""
        kept = None if self.following else self.cursor_key()
        top = self.scroll_y
        if rebuild or self.next_number is None:
            self.clear()
            self.events.clear()
            self.next_number = first
        # Rows are added in number order, so the buffer's losses lead.
        removed = 0
        for key in list(self.events):
            if int(key) >= first:
                break
            self.remove_row(key)
            del self.events[key]
            removed += 1
        for number in range(max(self.next_number, first), first + len(buffered)):
            event = buffered[number - first]
            if accept(event):
                key = str(number)
                self.events[key] = event
                # A label or a field's value is text, never markup.
                self.add_row(
                    *(
                        Text(cell) if isinstance(cell, str) else cell
                        for cell in event_row(event, project_label)
                    ),
                    key=key,
                )
        self.next_number = first + len(buffered)
        if self.following:
            self.move_to_newest()
        elif kept is not None and kept in self.events:
            # Removing older rows moved every row up; the cursor stays on
            # the event it was on, not on the row number.
            self.move_cursor(
                row=self.get_row_index(kept), animate=False, scroll=rebuild
            )
            if not rebuild:
                # A person may have scrolled away from the cursor, which the
                # table scrolls back into view once it has moved, after the
                # next refresh; the view moves up with its rows instead.
                self.call_after_refresh(
                    self.scroll_to, y=max(0, top - removed), animate=False
                )

    def cursor_key(self) -> str | None:
        """The key of the row under the cursor, if any."""
        if not self.row_count:
            return None
        return self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value

    def move_to_newest(self) -> None:
        if self.row_count:
            self.move_cursor(row=self.row_count - 1, animate=False)
            self.call_after_refresh(self.scroll_end, animate=False, x_axis=False)

    def set_following(self, following: bool) -> None:
        if following != self.following:
            self.following = following
            self.post_message(self.FollowChanged())

    def moved_by_hand(self) -> None:
        """Follow while a person's cursor is on the newest event, and not otherwise."""
        self.set_following(self.cursor_row == self.row_count - 1)

    # The table moves its own cursor as rows arrive, so only a person's
    # keys, clicks and scrolling stop it following; its highlights cannot.
    @override
    def action_cursor_up(self) -> None:
        super().action_cursor_up()
        self.moved_by_hand()

    @override
    def action_cursor_down(self) -> None:
        super().action_cursor_down()
        self.moved_by_hand()

    @override
    def action_page_up(self) -> None:
        super().action_page_up()
        self.moved_by_hand()

    @override
    def action_page_down(self) -> None:
        super().action_page_down()
        self.moved_by_hand()

    @override
    def action_scroll_top(self) -> None:
        super().action_scroll_top()
        self.moved_by_hand()

    @override
    def action_scroll_bottom(self) -> None:
        super().action_scroll_bottom()
        self.moved_by_hand()

    def on_click(self, _event: events.Click) -> None:
        # DataTable moves its cursor in its own handler, which runs after
        # this subclass's.
        self.call_later(self.moved_by_hand)

    def on_mouse_scroll_up(self, _event: events.MouseScrollUp) -> None:
        self.set_following(False)

    def on_scroll_up(self, _event: ScrollUp) -> None:
        # A click on the scrollbar above its thumb.
        self.set_following(False)

    def on_scroll_to(self, event: ScrollTo) -> None:
        # Dragging the scrollbar's thumb up from the bottom.
        if event.y is not None and event.y < self.max_scroll_y:
            self.set_following(False)

    def action_follow(self) -> None:
        """Move to the newest event and follow new events again."""
        self.move_to_newest()
        self.set_following(True)

    class FollowChanged(Message):
        """The table started or stopped following the newest event."""


class EventsSubject(Protocol):
    """What the Events tab reads from the dashboard, and the filter it keeps there."""

    @property
    def event_log(self) -> EventLog:
        """This run's Event Log, whose buffer holds the recent Runtime Events."""
        ...

    runtime_event_filter: EventFilter

    def project_label(self, project_id: str) -> str:
        """The Project's label, or its identity when it is no longer observed."""
        ...


class EventsPane(Vertical):
    """The filter bar over the event table and the selected event's detail."""

    def __init__(self, subject: EventsSubject, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.subject = subject
        # The filter and the level it was applied at that the rows show.
        self.shown: tuple[EventFilter, EventLevel | None] | None = None
        # The row whose event the detail pane shows.
        self.detail_key: str | None = None

    @override
    def compose(self) -> ComposeResult:
        chosen = self.subject.runtime_event_filter
        with Horizontal(id="runtime-event-filters"):
            yield Select(
                SHOW_OPTIONS,
                value=chosen.show,
                allow_blank=False,
                compact=True,
                id="runtime-show",
            )
            yield Select(
                KIND_OPTIONS,
                value=chosen.kind,
                allow_blank=False,
                compact=True,
                id="runtime-kind",
            )
            yield MarkedCheckbox(
                "Errors only", chosen.errors_only, compact=True, id="runtime-errors"
            )
            yield Static(FOLLOWING, id="runtime-follow")
        with Horizontal(id="runtime-event-panes"):
            yield EventTable(id="runtime-event-table")
            yield DetailFields(id="runtime-event-detail")

    def on_mount(self) -> None:
        self.query_one("#runtime-event-detail").border_title = "EVENT"

    @property
    def table(self) -> EventTable:
        return self.query_one(EventTable)

    def update_events(self) -> None:
        """Show the buffer as it stands under the chosen filter."""
        log = self.subject.event_log
        chosen = self.subject.runtime_event_filter
        level = log.level
        # Only the recorded filter depends on the level, so only it is
        # applied again when the level changes.
        shown = (chosen, level if chosen.show == "recorded" else None)
        rebuild = shown != self.shown
        self.shown = shown
        first, buffered = log.numbered_recent_events()
        table = self.table
        table.sync(
            first,
            buffered,
            accept=lambda event: accepts(chosen, event, level),
            project_label=self.subject.project_label,
            rebuild=rebuild,
        )
        if not table.row_count:
            message = "no events match these filters" if buffered else "no events yet"
            self.detail_key = None
            self.show_detail(DetailItem(message, kind="message"))
        else:
            # The event under a paused cursor can leave the buffer without
            # the cursor's row changing, so no highlight would report it.
            self.show_event(table.cursor_key())

    def show_detail(self, *items: DetailItem) -> None:
        self.query_one("#runtime-event-detail", DetailFields).update(*items)

    def choose(self, chosen: EventFilter) -> None:
        if chosen == self.subject.runtime_event_filter:
            return
        self.subject.runtime_event_filter = chosen
        self.update_events()

    @on(Select.Changed, "#runtime-show")
    def choose_show(self, event: Select.Changed) -> None:
        show = cast("EventShow", event.value)
        self.choose(replace(self.subject.runtime_event_filter, show=show))

    @on(Select.Changed, "#runtime-kind")
    def choose_kind(self, event: Select.Changed) -> None:
        self.choose(replace(self.subject.runtime_event_filter, kind=str(event.value)))

    @on(Checkbox.Changed, "#runtime-errors")
    def choose_errors_only(self, event: Checkbox.Changed) -> None:
        self.choose(replace(self.subject.runtime_event_filter, errors_only=event.value))

    @on(DataTable.RowHighlighted, "#runtime-event-table")
    def highlight(self, event: DataTable.RowHighlighted) -> None:
        self.show_event(event.row_key.value)

    def show_event(self, key: str | None) -> None:
        """Show the detail of the event in row ``key``, unless it is shown already."""
        found = None if key is None else self.table.events.get(key)
        if found is not None and key != self.detail_key:
            self.detail_key = key
            self.show_detail(*event_detail(found))

    @on(EventTable.FollowChanged)
    def follow_changed(self) -> None:
        self.show_following()

    def show_following(self) -> None:
        text = FOLLOWING if self.table.following else PAUSED
        self.query_one("#runtime-follow", Static).update(text)
