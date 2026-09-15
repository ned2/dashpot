"""Retain bounded accepted pages without reconstructing evicted history.

The two ``*_text`` functions say where a navigation stands and what a
Project's totals are, in the words the panes' titles and notes use.
"""

from __future__ import annotations

from dataclasses import dataclass

from .source_queries import ProjectTotals, QueryPage, QueryRequest


@dataclass(frozen=True, slots=True)
class PageTicket:
    generation: int
    request: QueryRequest
    navigation: bool = False


class PageNavigation:
    def __init__(self, request: QueryRequest, capacity: int = 8) -> None:
        self.request = request
        self.capacity = capacity
        self.generation = 0
        self.history: list[QueryPage] = []
        self.index = -1
        self.error: str | None = None
        self.evicted = False

    @property
    def page(self) -> QueryPage | None:
        return self.history[self.index] if self.index >= 0 else None

    def restart(self, request: QueryRequest | None = None) -> PageTicket:
        """Start a new navigation generation at page one."""
        self.generation += 1
        self.request = (request or self.request).model_copy(update={"cursor": None})
        self.history = []
        self.index = -1
        self.evicted = False
        self.error = None
        return PageTicket(self.generation, self.request)

    def refresh(self) -> PageTicket:
        """Repeat the displayed request without superseding current user work."""
        return PageTicket(
            self.generation, self.page.request if self.page else self.request
        )

    def next(self) -> PageTicket | None:
        """Navigate using the accepted page's continuation only."""
        page = self.page
        if page is None or page.next_cursor is None:
            self.error = (
                "Narrow the query to see more results"
                if page and page.continuation == "provider-limit"
                else "No next page"
            )
            return None
        self.generation += 1
        self.error = None
        if self.index + 1 < len(self.history):
            self.index += 1
            self.request = self.page.request if self.page else self.request
            return None
        self.request = page.request.model_copy(update={"cursor": page.next_cursor})
        return PageTicket(self.generation, self.request, navigation=True)

    def previous(self) -> None:
        """Return to a retained observation with its original timestamp."""
        self.generation += 1
        if self.index <= 0:
            self.error = (
                "Earlier page evicted; restart from page one"
                if self.evicted
                else "Already at first page"
            )
            return
        self.index -= 1
        self.request = self.history[self.index].request
        self.error = None

    def accept(
        self, ticket: PageTicket, page: QueryPage | None, error: str | None = None
    ) -> bool:
        """Reject superseded results and preserve the accepted page on navigation failure."""
        if ticket.generation != self.generation:
            return False
        if (
            error
            or page is None
            or (ticket.navigation and page.status == "unavailable")
        ):
            self.error = (
                error or "; ".join(d.message for d in page.diagnostics)
                if page
                else error
            )
            return True
        self.error = None
        if ticket.navigation or self.index < 0:
            self.history = self.history[: self.index + 1]
            self.history.append(page)
            self.index += 1
        else:
            self.history[self.index] = page
            self.history = self.history[: self.index + 1]
        if len(self.history) > self.capacity:
            self.history.pop(0)
            self.index -= 1
            self.evicted = True
        return True


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
