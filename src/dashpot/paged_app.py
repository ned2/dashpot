"""Present independently observed source pages in the dashboard."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from typing import ClassVar, cast

from rich.text import Text
from textual import work
from textual.binding import BindingType
from textual.content import Content
from textual.message import Message
from textual.widgets import DataTable, Input, Static
from typing_extensions import override

from .alerts import summarize_alerts
from .app import DashboardScreen, DashpotApp, ObservationFinished, PaneRows
from .cleanup import CleanupAdapter
from .collect import ObservationScheduler, SnapshotCollector
from .fetch import RemoteFetcher
from .issue_list import IssueListQuery, IssueListResult, row_key
from .issue_table import (
    COLUMNS_BY_KEY,
    ColumnKey,
    IssueTableViewState,
    SortTerm,
    TableCell,
    column_header,
)
from .issue_view import IssueScreen
from .observation_store import WorkspaceObservationStore
from .page_navigation import PageNavigation, PageTicket
from .paged_store import PagedObservationStore
from .pull_request_cells import build_pull_request_rows
from .pull_request_list import (
    PullRequestListQuery,
    PullRequestListResult,
    PullRequestListRow,
)
from .source_queries import (
    ProjectTotals,
    QueryPage,
    QueryRequest,
    QuerySource,
    ResolvedIssue,
    ResourceKind,
)
from .worktree_launcher import LauncherConfiguration


class QueryFinished(Message):
    def __init__(
        self, key: str, ticket: PageTicket | None, value: object, error: str | None
    ) -> None:
        super().__init__()
        self.key, self.ticket, self.value, self.error = key, ticket, value, error


def totals_text(totals: ProjectTotals | None) -> str:
    """Report Project totals without substituting page length or zero."""
    if totals is None or totals.open_count is None or totals.closed_count is None:
        return "Open ? · Closed ? · totals unavailable"
    return f"Open {totals.open_count} · Closed {totals.closed_count}" + (
        " · stale totals" if totals.status == "stale" else ""
    )


def page_text(navigation: PageNavigation) -> str:
    """Describe matching scope, coverage and the accepted page's own age."""
    page = navigation.page
    if page is None:
        return navigation.error or "Loading page"
    text = f"{page.returned_count} shown · {page.matched_count if page.matched_count is not None else '?'} matches · {page.status}"
    if page.last_good_at:
        text += f" · observed {page.last_good_at}"
    if (
        page.result_limit
        and page.matched_count
        and page.matched_count > page.result_limit
    ):
        text += f" · first {page.result_limit:,} accessible; narrow query"
    if navigation.error:
        text += f" · {navigation.error}"
    return text


class PagedDashboardScreen(DashboardScreen):
    BINDINGS: ClassVar[list[BindingType]] = [
        *DashboardScreen.BINDINGS,
        ("n", "next_page", "Next page"),
        ("p", "previous_page", "Previous page"),
        ("home", "restart_page", "First page"),
    ]

    @property
    @override
    def dashpot(self) -> PagedDashpotApp:
        return cast("PagedDashpotApp", self.app)

    def page_kind(self) -> ResourceKind:
        """Choose the page belonging to the focused query pane."""
        return (
            "pull-requests" if self.pull_requests_pane().has_focus_within else "issues"
        )

    def action_next_page(self) -> None:
        kind = self.page_kind()
        ticket = self.dashpot.navigation[kind].next()
        if ticket:
            self.dashpot.request_page(kind, ticket)
        self.dashpot.render_pages()

    def action_previous_page(self) -> None:
        self.dashpot.navigation[self.page_kind()].previous()
        self.dashpot.render_pages()

    def action_restart_page(self) -> None:
        kind = self.page_kind()
        self.dashpot.request_page(kind, self.dashpot.navigation[kind].restart())

    @override
    def on_input_changed(self, event: Input.Changed) -> None:
        """Keep editable source text separate from submitted queries."""
        return

    @override
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "issue-search":
            event.stop()
            self.set_issue_query(replace(self.issue_view.query, text=event.value))
            self.dashpot.submit_page("issues", query=event.value)
        elif event.input.id == "pull-request-search":
            event.stop()
            self.set_pull_request_query(
                replace(self.pull_request_query, text=event.value)
            )
            self.dashpot.submit_page("pull-requests", query=event.value)

    @override
    def set_issue_query(
        self, query: IssueListQuery, *, sort: tuple[SortTerm, ...] | None = None
    ) -> None:
        previous = self.issue_view.query
        self.issue_view = replace(self.issue_view, query=query, sort=())
        if query.states != previous.states:
            state = "all" if len(query.states) == 2 else next(iter(query.states))
            self.dashpot.submit_page("issues", state=state)

    @override
    def set_pull_request_query(self, query: PullRequestListQuery) -> None:
        previous = self.pull_request_query
        self.pull_request_query = query
        if query.states != previous.states:
            state = "all" if len(query.states) == 2 else next(iter(query.states))
            self.dashpot.submit_page("pull-requests", state=state)

    @override
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "queue":
            return
        column = str(event.column_key.value)
        navigation = self.dashpot.navigation["issues"]
        source = self.dashpot.sources["issues"]
        if not source.supports_sort(navigation.request, column):
            self.notify(
                "This column cannot order the submitted source query",
                severity="information",
            )
            return
        if (
            column not in COLUMNS_BY_KEY
            or not COLUMNS_BY_KEY[cast("ColumnKey", column)].sortable
        ):
            return
        direction = "desc" if navigation.request.ordering == f"{column}:asc" else "asc"
        self.dashpot.submit_page("issues", ordering=f"{column}:{direction}")

    @override
    def update_sort_headers(self, table: DataTable[TableCell]) -> None:
        request = self.dashpot.navigation["issues"].request
        source = self.dashpot.sources["issues"]
        for key, column in table.columns.items():
            name = cast("ColumnKey", str(key.value))
            spec = COLUMNS_BY_KEY[name]
            if not source.supports_sort(request, name):
                column.label = Text(spec.label)
            else:
                term = (
                    (SortTerm(name, request.ordering.endswith(":desc")),)
                    if request.ordering.startswith(name + ":")
                    else ()
                )
                column.label = column_header(spec, term)
        table.refresh()

    @override
    def sort_rows(self, table: DataTable[TableCell]) -> None:
        """Preserve source ordering rather than sorting the displayed page."""
        return

    @override
    def reconcile_rows(self) -> IssueListResult:
        # Provider order can change with identical row identities. Rebuild the
        # small page so keyed-table insertion history never becomes ordering.
        self.queue_table().clear()
        self.rendered_cells = {}
        result = super().reconcile_rows()
        self.query_one("#issue-count", Static).update(
            page_text(self.dashpot.navigation["issues"])
        )
        self.update_sort_headers(self.queue_table())
        return result

    @override
    def update_issue_inventory(self, result: IssueListResult) -> None:
        self.query_one("#queue-pane").border_title = Content(
            "ISSUES · " + totals_text(self.dashpot.paged_store.totals.get("issues"))
        )

    @override
    def _pull_request_pane_rows(
        self, store: WorkspaceObservationStore, *, dark: bool, now: datetime
    ) -> PaneRows:
        page = self.dashpot.paged_store.pages.get("pull-requests")
        projects = store.projects()
        if page is None or not projects:
            return PaneRows(
                (),
                title_summary=totals_text(
                    self.dashpot.paged_store.totals.get("pull-requests")
                ),
                empty_message="Loading page",
            )
        result = PullRequestListResult(
            tuple(
                PullRequestListRow(row_key("pull-request", pr.id), projects[0], pr)
                for pr in page.pull_requests
            ),
            page.matched_count or 0,
            page.returned_count,
            page.status,
            page.attempted_at,
            page.last_good_at,
            0,
            0,
        )
        return PaneRows(
            build_pull_request_rows(result, dark=dark, now=now),
            title_summary=totals_text(
                self.dashpot.paged_store.totals.get("pull-requests")
            ),
            note=page_text(self.dashpot.navigation["pull-requests"]),
            empty_message="No matching Pull Requests"
            if page.status == "fresh"
            else "Pull Requests unavailable",
        )

    @override
    def update_alert(self) -> None:
        app = self.dashpot
        alert = summarize_alerts(
            app.store,
            failures=app.observation_errors,
            refreshing=tuple(app.in_flight) if app.refreshing_visible else (),
            fetching=tuple(app.fetching),
            source_pages=app.paged_store.pages,
        )
        widget = self.query_one("#alert", Static)
        widget.set_class(alert is not None, "-visible")
        for severity in ("error", "warning", "info"):
            widget.set_class(
                alert is not None and alert.severity == severity, f"-{severity}"
            )
        widget.update(alert.text if alert else "")

    @override
    def open_issue(self, key: str) -> None:
        super().open_issue(key)
        row = self.rows_by_key.get(key)
        if row:
            self.dashpot.selected_identity = row.issue.id
            self.dashpot.request_identities()

    @override
    def highlight_issue(self, issue_id: str | None) -> None:
        if issue_id is None:
            return
        self.dashpot.selected_identity = issue_id
        row = self.dashpot.paged_store._row(issue_id)
        if row:
            self.app.push_screen(IssueScreen(row))
        else:
            self.notify("Resolving bound Issue details")
            self.dashpot.open_when_resolved = issue_id
        self.dashpot.request_identities()


# The Query Sources the shipped app consults, one per concurrent consumer:
# each key runs on its own executor thread against its own source instance.
QUERY_SOURCE_KEYS: tuple[str, ...] = (
    "issues",
    "pull-requests",
    "totals:issues",
    "totals:pull-requests",
    "identities",
)


class PagedDashpotApp(DashpotApp):
    def __init__(
        self,
        collector: SnapshotCollector | ObservationScheduler,
        *,
        sources: Mapping[str, QuerySource],
        refresh_seconds: float = 15,
        fetcher: RemoteFetcher | None = None,
        cleaner: CleanupAdapter | None = None,
        launcher_configuration: LauncherConfiguration | None = None,
    ) -> None:
        self.paged_store = PagedObservationStore()
        self.navigation: dict[ResourceKind, PageNavigation] = {
            kind: PageNavigation(QueryRequest(kind=kind))
            for kind in ("issues", "pull-requests")
        }
        self.sources = dict(sources)
        self.query_executor = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="dashpot-query"
        )
        self.query_busy: set[str] = set()
        self.query_queued: dict[
            str, tuple[PageTicket | None, Callable[[], object]]
        ] = {}
        self.selected_identity: str | None = None
        self.open_when_resolved: str | None = None
        super().__init__(
            collector,
            observation_store=self.paged_store,
            refresh_seconds=refresh_seconds,
            issue_view=IssueTableViewState(sort=()),
            fetcher=fetcher,
            cleaner=cleaner,
            launcher_configuration=launcher_configuration,
        )
        # A local-only coordinator composes a placeholder for every Project
        # at construction; publishing it now names the Projects before their
        # first observation lands.
        self.scheduler.publish(self.paged_store)

    @override
    def get_default_screen(self) -> PagedDashboardScreen:
        return PagedDashboardScreen(
            self.initial_issue_view, (), self.initial_pull_request_query, ()
        )

    # Textual dispatches a message handler on every class of the MRO that
    # defines one, subclass first, so the handlers below never call super():
    # the base handler runs once, after this one, on its own.

    @override
    def on_ready(self) -> None:
        for kind, prefix in (("issues", "issue"), ("pull-requests", "pull-request")):
            source = self.sources[kind]
            self.dashboard.query_one(
                f"#{prefix}-search", Input
            ).placeholder = source.search_prompt
        if self.store.has_observations:
            # The base handler requests nothing over a seeded store, and the
            # placeholders published at construction are such a seed.
            self.request_refresh("initial")

    @override
    def request_refresh(self, trigger: str) -> None:
        super().request_refresh(trigger)
        for kind in ("issues", "pull-requests"):
            navigation = self.navigation[kind]
            if trigger == "manual":
                self.request_page(kind, navigation.restart())
            elif kind not in self.query_busy:
                self.request_page(kind, navigation.refresh())
            key = "totals:" + kind
            if key not in self.query_busy:
                self.launch_query(
                    key, None, lambda kind=kind, key=key: self.sources[key].totals(kind)
                )
        self.request_identities()

    def submit_page(self, kind: ResourceKind, **updates: str) -> None:
        """Submit a new query context and invalidate prior navigation history."""
        navigation = self.navigation[kind]
        self.request_page(
            kind, navigation.restart(navigation.request.model_copy(update=updates))
        )

    def request_page(self, kind: ResourceKind, ticket: PageTicket) -> None:
        self.launch_query(
            kind, ticket, lambda: self.sources[kind].query_page(ticket.request)
        )
        self.render_pages()

    def request_identities(self) -> None:
        ids = [
            run.issue_id
            for run in self.paged_store.checkpoint().agent_runs
            if run.issue_id
        ]
        if self.selected_identity:
            ids.append(self.selected_identity)
            row = self.paged_store._row(self.selected_identity)
            if row:
                relationships = row.issue.relationships
                ids.extend(
                    (
                        *relationships.sub_issues,
                        *relationships.blocked_by,
                        *relationships.blocking,
                    )
                )
                if relationships.parent:
                    ids.append(relationships.parent)
        requested = tuple(dict.fromkeys(ids))
        if requested:
            self.launch_query(
                "identities",
                None,
                lambda: self.sources["identities"].resolve_identities(requested),
            )

    def launch_query(
        self, key: str, ticket: PageTicket | None, operation: Callable[[], object]
    ) -> None:
        if key in self.query_busy:
            self.query_queued[key] = (ticket, operation)
            return
        self.query_busy.add(key)
        self.run_query(key, ticket, operation)

    @work(exit_on_error=False)
    async def run_query(
        self, key: str, ticket: PageTicket | None, operation: Callable[[], object]
    ) -> None:
        try:
            value = await asyncio.get_running_loop().run_in_executor(
                self.query_executor, operation
            )
            error = None
        except Exception as exc:
            value, error = None, str(exc)
        self.post_message(QueryFinished(key, ticket, value, error))

    def on_query_finished(self, message: QueryFinished) -> None:
        self.query_busy.discard(message.key)
        if message.ticket:
            kind = cast("ResourceKind", message.key)
            self.navigation[kind].accept(
                message.ticket, cast("QueryPage | None", message.value), message.error
            )
        elif isinstance(message.value, ProjectTotals):
            self.paged_store.totals[message.value.kind] = message.value
        elif message.key == "identities" and isinstance(message.value, tuple):
            self.paged_store.accept_identities(
                cast("tuple[ResolvedIssue, ...]", message.value)
            )
            if self.open_when_resolved and any(
                outcome.issue_id == self.open_when_resolved
                for outcome in cast("tuple[ResolvedIssue, ...]", message.value)
            ):
                row = self.paged_store._row(self.open_when_resolved)
                if row:
                    self.push_screen(IssueScreen(row))
                else:
                    self.notify(
                        "Bound Issue details are unavailable", severity="warning"
                    )
                self.open_when_resolved = None
        self.render_pages()
        queued = self.query_queued.pop(message.key, None)
        if queued:
            self.launch_query(message.key, *queued)

    def render_pages(self) -> None:
        for kind, navigation in self.navigation.items():
            if navigation.page:
                self.paged_store.pages[kind] = navigation.page
            else:
                self.paged_store.pages.pop(kind, None)
        if not self.is_running or not self.dashboard.is_mounted:
            return
        self.dashboard.queue_table().loading = False
        self.dashboard.update_issue_inventory(self.dashboard.reconcile_rows())
        self.dashboard.reconcile_list_panes()
        self.dashboard.update_diagnostics()
        if isinstance(self.screen, IssueScreen):
            screen = self.screen
            context = self.paged_store.detail_for(screen.context)
            if context and context != screen.context:
                screen.context = context
                screen.issue = context.issue
                screen.refresh(recompose=True)

    @override
    def _accept_observation(self, message: ObservationFinished) -> None:
        super()._accept_observation(message)
        # Identities are resolved against the Agent Runs just published.
        if message.ticket.key.kind == "agent-runs":
            self.request_identities()

    @override
    def on_unmount(self) -> None:
        self.query_executor.shutdown(wait=False, cancel_futures=True)
