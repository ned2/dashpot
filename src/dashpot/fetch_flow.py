"""Run the Remote Fetch a person asks for with ``f``, one Project at a time.

The flow fetches only the Repository Anchor whose refs supplied a Project's
Branch observation, holds the Project while the fetch runs, and reports the
outcome; what the fetch changed is then observed the passive way rather
than inferred ([ADR 0014](../../docs/adr/0014-fetch-remotes-on-explicit-key-press.md)).
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .messages import FetchFinished, OffLoopHost
from .observation_runner import ObservationRunner
from .paged_store import PagedObservationStore

if TYPE_CHECKING:
    from textual.notifications import SeverityLevel

    from .fetch import RemoteFetcher


class FlowHost(OffLoopHost, Protocol):
    """What a mutating flow asks of the app beyond running work off the loop."""

    @property
    def closing(self) -> bool: ...

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: SeverityLevel = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None: ...

    def update_alert(self) -> None: ...

    def update_diagnostics(self) -> None: ...


class RemoteFetchFlow:
    """Hold each Project through its explicit Remote Fetch and report the outcome."""

    def __init__(
        self,
        fetcher: RemoteFetcher | None,
        store: PagedObservationStore,
        observations: ObservationRunner,
        host: FlowHost,
    ) -> None:
        # The explicit fetch seam (``f``); without one the key is refused,
        # so no observation-only construction can ever fetch.
        self.fetcher = fetcher
        self.store = store
        self.observations = observations
        self.host = host
        # Projects whose remotes are being fetched, by identity, and the last
        # fetch failure per Project until a fetch there succeeds.
        self.fetching: dict[str, str] = {}
        self.errors: dict[str, str] = {}

    def label(self, project_id: str) -> str:
        """Name a Project by its display label, or its identity when unobserved."""
        project = self.store.project(project_id)
        return project.display_label if project is not None else project_id

    def request(self, *, held: Mapping[str, str]) -> None:
        """Fetch the remotes of every observed Project's authoritative anchor.

        Only the Repository Anchor whose refs supplied the Branch observation
        is fetched, so independent clones sharing a Project are left alone.
        A Project already being fetched, or one ``held`` by a Cleanup, is
        refused rather than fetched twice or under a mutation.
        """
        fetcher = self.fetcher
        if fetcher is None:
            self.host.notify(
                "Fetching is not available in this view",
                severity="warning",
                title="Dashpot fetch",
            )
            return
        anchors = {
            project.project_id: project.snapshot.branch_anchor
            for project in self.store.projects()
            if project.snapshot is not None
            and project.snapshot.branch_anchor is not None
        }
        if not anchors:
            self.host.notify(
                "No Branch observation names a Repository Anchor to fetch yet",
                severity="warning",
                title="Dashpot fetch",
            )
            return
        for project_id, anchor in anchors.items():
            if project_id in held:
                self.host.notify(
                    f"Cleaning up {self.label(project_id)}; fetch after it finishes",
                    severity="warning",
                    title="Dashpot fetch",
                )
                continue
            if project_id in self.fetching:
                self.host.notify(
                    f"Already fetching {self.label(project_id)}",
                    severity="warning",
                    title="Dashpot fetch",
                )
                continue
            self.fetching[project_id] = anchor
            self.host.run_off_loop(
                f"fetch {project_id}",
                f"fetch:{project_id}",
                partial(fetcher, Path(anchor)),
                partial(FetchFinished, project_id),
            )
        self.host.update_alert()

    def record(
        self, message: FetchFinished, *, release: bool = True, observe: bool = True
    ) -> None:
        """Report a Remote Fetch and optionally release its Project reservation."""
        if self.host.closing:
            return
        if release:
            self.fetching.pop(message.project_id, None)
        label = self.label(message.project_id)
        report = message.report
        if report is None or not report.succeeded:
            detail = message.error if report is None else report.summary()
            self.errors[message.project_id] = f"Fetch failed: {label}: {detail}"
            self.host.notify(
                f"{label}: {detail}", severity="error", title="Dashpot fetch"
            )
        else:
            self.errors.pop(message.project_id, None)
            self.host.notify(
                f"{label}: {report.summary()}",
                severity="information",
                title="Dashpot fetch",
            )
        self.host.update_diagnostics()
        # Whatever a remote changed is observed the passive way: the Git state
        # is re-observed rather than inferred from the fetch, and a fetch
        # that reached no remote leaves the last good observation as it is.
        if observe and report is not None and report.fetched:
            self.observations.schedule(
                self.observations.git_keys(message.project_id), "fetch"
            )
        self.host.update_alert()
