"""Run the Cleanup a person asks for with ``x``: preview, confirm, perform, re-observe.

The flow holds a Project from the moment its preview is taken until the
modal is dismissed or the report is in, refuses a second Cleanup or a Remote
Fetch there meanwhile, and lets the open preview fetch its remotes and
rebuild its evidence without confirming anything
([ADR 0019](../../docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md),
[ADR 0036](../../docs/adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md)).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeVar

from textual.worker import get_current_worker

from ..observation.keys import ObservationKey
from ..observation.paged_store import PagedObservationStore
from ..repository.cleanup import (
    BranchCleanupRequest,
    CleanupAdapter,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    TargetResult,
    WorktreeCleanupRequest,
)
from .cleanup_view import CleanupReportScreen, CleanupScreen
from .fetch_flow import FlowHost, RemoteFetchFlow
from .messages import CleanupFinished, CleanupInspected, FetchFinished
from .observation_runner import ObservationRunner

if TYPE_CHECKING:
    from textual.screen import Screen

    from .messages import ObservationFinished

T = TypeVar("T")


class CleanupHost(FlowHost, Protocol):
    """What the Cleanup flow asks of the app: its screens and its workers."""

    @property
    def screen(self) -> Screen[Any]: ...

    @property
    def screen_stack(self) -> list[Screen[Any]]: ...

    def push_screen(
        self, screen: Screen[Any], callback: Callable[[Any], None] | None = None
    ) -> object: ...

    def run_worker(
        self,
        work: Callable[[], Any],
        *,
        name: str | None = "",
        group: str = "default",
        exit_on_error: bool = True,
    ) -> object: ...

    async def off_loop(self, operation: Callable[[], T]) -> T: ...


@dataclass(frozen=True, slots=True)
class CleanupSelection:
    """The pane row a person pressed ``x`` on: which list, and its row key."""

    kind: Literal["branch", "worktree"]
    key: str


@dataclass(frozen=True, slots=True)
class CleanupPreviewHold:
    """One Project's open preview and the Remote Fetch anchor captured with it."""

    screen: CleanupScreen
    anchor: Path | None


def cleanup_subject(request: CleanupRequest) -> str:
    """What a Cleanup in progress is about, for the refusals that name it."""
    if isinstance(request, BranchCleanupRequest):
        return request.name
    return str(request.path)


def cleanup_result_line(result: TargetResult) -> str:
    """Render one concise Cleanup outcome for a toast."""
    if result.outcome == "deleted":
        verb = "Removed" if result.kind == "worktree" else "Deleted"
        return f"{verb} {result.label}"
    if result.outcome == "already-absent":
        return f"{result.label} already absent"
    return f"{result.outcome.capitalize()} {result.label}"


def cleanup_summary(report: CleanupReport) -> str:
    """List each target's outcome for a toast, or why nothing ran."""
    if report.refusals:
        return "\n".join(report.refusals)
    return "\n".join(cleanup_result_line(result) for result in report.results)


class CleanupFlow:
    """Hold each Project through its Cleanup, from preview to report."""

    def __init__(
        self,
        cleaner: CleanupAdapter | None,
        store: PagedObservationStore,
        observations: ObservationRunner,
        fetches: RemoteFetchFlow,
        host: CleanupHost,
    ) -> None:
        # The explicit Cleanup seam (``x``): without one the key is refused,
        # so no observation-only construction can ever delete.
        self.cleaner = cleaner
        self.store = store
        self.observations = observations
        self.fetches = fetches
        self.host = host
        # Projects with a Cleanup in progress, from the preview being taken
        # until the modal is dismissed or the report is in, by the subject
        # the refusals name; a fetch there is refused meanwhile, and a
        # Cleanup while a fetch is in flight.
        self.cleaning: dict[str, str] = {}
        self.previews: dict[str, CleanupPreviewHold] = {}
        self._refresh_waiters: list[
            tuple[dict[ObservationKey, int], asyncio.Future[None]]
        ] = []
        self.refresh_timeout = 30.0
        observations.landings.append(self.finish_observation)

    def request(self, selection: CleanupSelection | None) -> None:
        """Preview a Cleanup of the highlighted row, off the event loop.

        The row is resolved through the observation store to a Cleanup
        request at the Project's Branch anchor (a Branch) or the Repository
        the path belongs to (a Worktree). A Project being fetched, or already
        in a Cleanup, is refused rather than mutated twice.
        """
        cleaner = self.cleaner
        if cleaner is None:
            self.host.notify(
                "Deleting is not available in this view",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        if selection is None:
            self.host.notify(
                "Highlight a Branch or a Worktree to delete",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        resolved = self.resolve_request(selection)
        if resolved is None:
            self.host.notify(
                "The highlighted row is no longer observed",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        project_id, request = resolved
        label = self.fetches.label(project_id)
        if project_id in self.fetches.fetching:
            self.host.notify(
                f"Fetching {label}; delete after it finishes",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        if project_id in self.cleaning:
            self.host.notify(
                f"Already cleaning up {label}",
                severity="warning",
                title="Dashpot cleanup",
            )
            return
        self.cleaning[project_id] = cleanup_subject(request)
        self.host.run_off_loop(
            f"inspect cleanup {project_id}",
            f"cleanup:{project_id}",
            partial(cleaner.inspect, request, protected=self.protection(project_id)),
            partial(CleanupInspected, project_id, request),
        )

    def resolve_request(
        self, selection: CleanupSelection
    ) -> tuple[str, CleanupRequest] | None:
        """Turn a highlighted row into the Cleanup request its observation names."""
        if selection.kind == "branch":
            for branch_row in self.store.query_branches().rows:
                if branch_row.key != selection.key:
                    continue
                snapshot = branch_row.project.snapshot
                anchor = snapshot.branch_anchor if snapshot is not None else None
                if anchor is None:
                    return None
                return branch_row.project.project_id, BranchCleanupRequest(
                    Path(anchor), branch_row.name
                )
            return None
        for worktree_row in self.store.query_worktrees().rows:
            if worktree_row.key == selection.key:
                return worktree_row.project.project_id, WorktreeCleanupRequest(
                    Path(worktree_row.project.primary_anchor),
                    Path(worktree_row.target.path),
                )
        return None

    def protection(self, project_id: str) -> tuple[Path, ...]:
        """The checkouts a Cleanup never removes: Dashpot's own and the anchors."""
        project = self.store.project(project_id)
        anchors = tuple(Path(anchor) for anchor in project.anchors) if project else ()
        return (Path.cwd().resolve(), *anchors)

    def release(self, project_id: str) -> None:
        """Let the Project go: no preview is open and no Cleanup is in progress."""
        self.previews.pop(project_id, None)
        self.cleaning.pop(project_id, None)

    def holds(self, project_id: str, screen: CleanupScreen) -> bool:
        """Whether ``screen`` is still the preview held for the Project."""
        hold = self.previews.get(project_id)
        return hold is not None and hold.screen is screen

    def finish_inspection(self, message: CleanupInspected) -> None:
        """Show the preview an inspection produced, or report why there is none."""
        if self.host.closing:
            return
        if message.preview is None:
            self.release(message.project_id)
            self.host.notify(
                f"{self.fetches.label(message.project_id)}: {message.error}",
                severity="error",
                title="Dashpot cleanup",
            )
            return
        self.show_preview(message.project_id, message.request, message.preview)

    def show_preview(
        self,
        project_id: str,
        request: CleanupRequest,
        preview: CleanupPreview,
        *,
        changed: bool = False,
    ) -> None:
        """Capture the preview's Project and Remote Fetch anchor once."""
        project = self.store.project(project_id)
        screen = CleanupScreen(
            request,
            preview,
            changed=changed,
            fetched_at=project.snapshot.fetched_at
            if project and project.snapshot
            else None,
        )
        anchor = (
            project.snapshot.branch_anchor if project and project.snapshot else None
        )
        captured_anchor = Path(anchor) if anchor else None
        previous = self.previews.get(project_id)
        if changed and previous is not None:
            screen.primary_identity = previous.screen.primary_identity
            captured_anchor = previous.anchor
        self.previews[project_id] = CleanupPreviewHold(screen, captured_anchor)
        self.host.push_screen(screen, partial(self.confirm, project_id))

    def fetch_requested(self, screen: CleanupScreen) -> None:
        """Fetch the remotes behind an open preview, when nothing forbids it."""
        owner = next(
            (
                (project_id, hold.anchor)
                for project_id, hold in self.previews.items()
                if hold.screen is screen
            ),
            None,
        )
        if owner is None or self.host.screen is not screen or screen.busy:
            return
        project_id, anchor = owner
        if self.fetches.fetcher is None or anchor is None:
            screen.fetch_status = (
                "Remote Fetch is unavailable in this view."
                if self.fetches.fetcher is None
                else "No Repository Anchor supplies this Project's Branch facts. Refresh and reopen the preview."
            )
            return
        if project_id in self.fetches.fetching:
            screen.fetch_status = "A Remote Fetch is already running for this Project."
            return
        if project_id not in self.cleaning:
            return
        screen.begin_fetch()
        self.fetches.hold(project_id, anchor)
        self.host.run_worker(
            partial(self.fetch_preview, project_id, anchor, screen),
            name=f"fetch cleanup preview {project_id}",
            group=f"fetch:{project_id}",
            exit_on_error=False,
        )
        self.host.update_alert()

    async def fetch_preview(
        self, project_id: str, anchor: Path, screen: CleanupScreen
    ) -> None:
        """Fetch, observe, and re-inspect one captured Cleanup without confirming it."""
        fetcher, cleaner = self.fetches.fetcher, self.cleaner
        assert fetcher is not None and cleaner is not None
        worker = get_current_worker()
        preview = None
        report = None
        error = None
        try:
            try:
                report = await self.host.off_loop(partial(fetcher, anchor))
            except Exception as exc:
                error = str(exc)
            if worker.is_cancelled or self.host.closing:
                return
            status = (
                report.summary() if report is not None else f"Fetch failed: {error}"
            )
            screen.verified_remotes = frozenset(
                report.fetched if report is not None else ()
            )
            self.fetches.record(
                FetchFinished(project_id, report=report, error=error),
                release=False,
                observe=False,
            )
            screen.fetch_status = (
                status + "\nRefreshing Git facts and Cleanup evidence…"
            )
            try:
                await self.observe_fetch(project_id)
                project = self.store.project(project_id)
                screen.fetched_at = (
                    project.snapshot.fetched_at
                    if project and project.snapshot
                    else None
                )
                if self.holds(project_id, screen):
                    preview = await self.host.off_loop(
                        partial(
                            cleaner.inspect,
                            screen.request,
                            protected=self.protection(project_id),
                        )
                    )
            except Exception as exc:
                detail = str(exc) or "Refresh timed out; retry or cancel."
                status += f"\nCould not refresh the preview: {detail}"
            if self.holds(project_id, screen) and screen in self.host.screen_stack:
                await screen.replace_preview(preview, status)
        finally:
            self.fetches.release(project_id)
            self.host.update_alert()

    async def observe_fetch(self, project_id: str) -> None:
        """Wait for post-fetch Git observations before accepting refreshed evidence."""
        keys = self.observations.git_keys(project_id)
        if not keys:
            raise RuntimeError(
                "No Git observation is available; refresh and reopen the preview."
            )
        pending = {key: self.observations.in_flight.get(key, 0) for key in keys}
        future = asyncio.Future[None]()
        waiter = (pending, future)
        self._refresh_waiters.append(waiter)
        try:
            self.observations.schedule(keys, "fetch", rerun_in_flight=True)
            await asyncio.wait_for(future, self.refresh_timeout)
        finally:
            self._refresh_waiters.remove(waiter)
        project = self.store.project(project_id)
        if (
            project is None
            or project.snapshot is None
            or project.snapshot.target_status != "fresh"
        ):
            raise RuntimeError(
                "Git observation is unavailable or stale; inspect Diagnostics and retry."
            )

    def finish_observation(self, message: ObservationFinished) -> None:
        """Resolve only post-fetch observation completions after publication."""
        key = message.ticket.key
        for pending, future in self._refresh_waiters:
            if (
                future.done()
                or key not in pending
                or message.ticket.generation <= pending[key]
            ):
                continue
            if message.error or message.outcome is None or not message.outcome.accepted:
                future.set_exception(
                    RuntimeError(message.error or "Git refresh was not accepted.")
                )
            else:
                del pending[key]
                if not pending:
                    future.set_result(None)

    def confirm(
        self, project_id: str, confirmation: CleanupConfirmation | None
    ) -> None:
        """Perform what the modal confirmed, or release the Project on cancel."""
        if confirmation is None:
            self.release(project_id)
            return
        if project_id in self.fetches.fetching:
            self.release(project_id)
            self.host.notify(
                "Remote Fetch is still running; reopen Cleanup after it finishes.",
                severity="warning",
            )
            return
        cleaner = self.cleaner
        if cleaner is None:  # pragma: no cover - request refuses first.
            return
        self.host.run_off_loop(
            f"perform cleanup {project_id}",
            f"cleanup:{project_id}",
            partial(
                cleaner.perform,
                confirmation,
                protected=self.protection(project_id),
            ),
            partial(CleanupFinished, project_id, confirmation),
        )

    def finish_cleanup(self, message: CleanupFinished) -> None:
        """Report a performed Cleanup, or hold the Project for a revised preview."""
        if self.host.closing:
            return
        label = self.fetches.label(message.project_id)
        report = message.report
        if report is None:
            self.release(message.project_id)
            self.host.notify(
                f"{label}: {message.error}", severity="error", title="Dashpot cleanup"
            )
            # The adapter may have mutated before failing: re-observe anyway.
            self.reobserve(message.project_id)
            return
        if report.changed:
            # The Project stays held: the revised preview needs another
            # explicit confirmation, and nothing was performed.
            self.host.notify(
                f"{label}: {report.refusals[0]}",
                severity="warning",
                title="Dashpot cleanup",
            )
            self.show_preview(
                message.project_id,
                message.confirmation.request,
                report.preview,
                changed=True,
            )
            return
        self.release(message.project_id)
        self.host.notify(
            cleanup_summary(report),
            severity="information" if report.succeeded else "error",
            title=f"{label} cleanup",
        )
        if not report.succeeded:
            # A successful report is already complete in the toast. Keep the
            # detailed screen only where a person needs the refusal or unknown
            # outcome and its recovery context.
            self.host.push_screen(CleanupReportScreen(report))
        if report.performed:
            self.reobserve(message.project_id)

    def reobserve(self, project_id: str) -> None:
        """Observe what a Cleanup changed the passive way, never inferring it."""
        self.observations.schedule(self.observations.git_keys(project_id), "cleanup")
