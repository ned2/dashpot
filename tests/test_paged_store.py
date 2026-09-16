"""The paged store joins each page row with its Project, across a transfer."""

from __future__ import annotations

from app_harness import (
    SnapshotQuerySource,
    issue,
    with_first_project,
    workspace_snapshot,
)
from dashpot.core.model import WorkspaceSnapshot
from dashpot.paged_store import PagedObservationStore
from dashpot.queries.source_queries import QueryPage, QueryRequest
from helpers import snapshot_of


def transfer() -> tuple[PagedObservationStore, SnapshotQuerySource]:
    """A store showing one Project's page, and a source observing the Issue moved."""
    transferred = issue("old/repository#7", "Transfer me")
    first = workspace_snapshot(transferred)
    moved = issue(
        "new/repository#70",
        "Transfer me",
        id=transferred.id,
        projectId="project:new-repository",
    )
    second = with_first_project(
        first,
        project_id="project:new-repository",
        display_label="New Repository",
        snapshot=snapshot_of(first.projects[0]).model_copy(update={"issues": (moved,)}),
    )
    store = PagedObservationStore(first)
    source = SnapshotQuerySource(first)
    store.accept_page("issues", page(source))
    source.serve(second)
    return store, source


def page(source: SnapshotQuerySource) -> QueryPage:
    return source.query_page(QueryRequest(kind="issues"))


def observed(source: SnapshotQuerySource) -> WorkspaceSnapshot:
    """The Workspace Snapshot the collector observes once the source has moved on."""
    return workspace_snapshot().model_copy(update={"projects": (source.project,)})


def titles(store: PagedObservationStore) -> list[str]:
    return [
        f"{row.project.display_label}: #{row.issue.number}"
        for row in store.query_issues().rows
    ]


def test_a_transferred_issue_keeps_its_row_while_its_page_is_in_flight() -> None:
    store, source = transfer()
    assert titles(store) == ["Test Repository: #7"]

    # The Project observation names a Project the shown page does not while
    # the page is queried again: the row keeps the Project it last joined
    # with, and can still be detailed, until the refreshed page lands.
    shown = store.pages["issues"]
    store.accept_page("issues", shown, in_flight=True)
    store.replace(observed(source))
    assert titles(store) == ["Test Repository: #7"]
    assert store.detail_for(store.query_issues().rows[0]) is not None
    store.accept_page("issues", shown, in_flight=True)
    assert titles(store) == ["Test Repository: #7"]

    store.accept_page("issues", page(source))
    assert titles(store) == ["New Repository: #70"]


def test_a_landed_page_joins_strictly() -> None:
    store, _source = transfer()
    stale = SnapshotQuerySource(store.checkpoint())

    # The Project leaves the Workspace while the page is in flight, and the
    # page that lands still names it: the row goes with the Project.
    store.accept_page("issues", store.pages["issues"], in_flight=True)
    store.replace(workspace_snapshot().model_copy(update={"projects": ()}))
    assert titles(store) == ["Test Repository: #7"]
    store.accept_page("issues", page(stale))
    assert titles(store) == []

    # A page that landed before the Projects changed is not in flight, so
    # the change joins it strictly too.
    store, _source = transfer()
    store.replace(workspace_snapshot().model_copy(update={"projects": ()}))
    assert titles(store) == []


def test_a_page_naming_a_project_never_observed_has_no_row() -> None:
    store, source = transfer()
    store.accept_page(
        "issues",
        page(source).model_copy(
            update={"issues": (issue("other#1", "Unknown", projectId="project:x"),)}
        ),
        in_flight=True,
    )
    assert titles(store) == []
    assert store.row_for("I_other#1") is None
