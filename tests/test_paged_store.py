"""The paged store joins each page row with its Project and its identity outcome."""

from __future__ import annotations

from typing import Literal

from app_harness import (
    SnapshotQuerySource,
    issue,
    with_first_project,
    workspace_snapshot,
)
from dashpot.core.model import Diagnostic, WorkspaceSnapshot
from dashpot.observation.paged_store import PagedObservationStore
from dashpot.queries.source_queries import (
    ProjectTotals,
    QueryPage,
    QueryRequest,
    ResolvedIssue,
)
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
    return source.query_page(QueryRequest(kind="issues")).page


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


BEFORE = "2026-08-25T00:59:00Z"
AFTER = "2026-08-25T01:01:00Z"


def outcome(
    source: SnapshotQuerySource,
    issue_id: str,
    observed_at: str,
    kind: Literal["not-resolved", "unavailable"] = "not-resolved",
) -> ResolvedIssue:
    """A fresh outcome for ``issue_id``, observed at ``observed_at``."""
    return ResolvedIssue(
        context=source.context,
        issue_id=issue_id,
        outcome=kind,
        status="fresh",
        attempted_at=observed_at,
        last_good_at=observed_at,
        diagnostics=(
            Diagnostic(
                source="github",
                severity="warning",
                code="issue-not-resolved",
                message=f"Issue {issue_id} is missing or inaccessible",
            ),
        )
        if kind == "not-resolved"
        else (),
    )


def listed_store() -> tuple[PagedObservationStore, SnapshotQuerySource, str]:
    """A store showing a page that lists one Issue, observed at the harness's NOW."""
    snapshot = workspace_snapshot(issue("test/repo#7", "Listed"))
    store = PagedObservationStore(snapshot)
    source = SnapshotQuerySource(snapshot)
    store.accept_page("issues", page(source))
    return store, source, snapshot_of(snapshot.projects[0]).issues[0].id


def test_a_page_listing_an_issue_wins_over_an_older_outcome() -> None:
    store, source, issue_id = listed_store()

    # The Issue was not resolved before the page observed it again, as when
    # its Local Issue file was briefly absent: the page lists it, so it has
    # a row, and the rows agree with the page's count.
    store.accept_identities((outcome(source, issue_id, BEFORE),))
    assert [row.issue.id for row in store.query_issues().rows] == [issue_id]
    assert store.row_for(issue_id) is not None

    # An unavailable outcome, however new, observed nothing to overrule it.
    store.accept_identities((outcome(source, issue_id, AFTER, "unavailable"),))
    assert store.row_for(issue_id) is not None
    # Neither listed nor resolved, an identity has no row.
    assert store.row_for("I_elsewhere") is None


def test_an_outcome_observed_after_the_page_overrules_it() -> None:
    store, source, issue_id = listed_store()

    store.accept_identities((outcome(source, issue_id, AFTER),))
    assert store.query_issues().rows == ()
    assert store.row_for(issue_id) is None

    # The page observing the Issue again, after the outcome, lists it again.
    later = store.pages["issues"].model_copy(
        update={"attempted_at": AFTER, "last_good_at": "2026-08-25T01:02:00Z"}
    )
    store.accept_page("issues", later)
    assert [row.issue.id for row in store.query_issues().rows] == [issue_id]


def test_only_the_identities_last_requested_keep_their_outcomes() -> None:
    store, source, issue_id = listed_store()
    store.accept_identities((outcome(source, "I_elsewhere", BEFORE),))
    assert "I_elsewhere" in store.resolved
    revision = store.source_revision
    assert any(
        entry.diagnostic.code == "issue-not-resolved" for entry in store.diagnostics()
    )

    # The selection moved on: the outcome no longer requested is forgotten,
    # with the Diagnostic it carried.
    store.accept_identities((outcome(source, issue_id, BEFORE, "unavailable"),))
    assert set(store.resolved) == {issue_id}
    assert store.source_revision == revision + 1
    assert not any(
        entry.diagnostic.code == "issue-not-resolved" for entry in store.diagnostics()
    )
    store.accept_identities(())
    assert store.resolved == {}
    store.accept_identities(())
    assert store.source_revision == revision + 2


def test_a_page_and_its_totals_reporting_alike_show_one_line() -> None:
    store, source, _issue_id = listed_store()
    unavailable = Diagnostic(
        source="local-markdown",
        severity="info",
        code="pull-requests-not-configured",
        message="Pull Requests are not configured for a Markdown Project",
    )
    store.accept_page(
        "pull-requests",
        store.pages["issues"].model_copy(
            update={
                "request": QueryRequest(kind="pull-requests"),
                "issues": (),
                "auxiliary": {},
                "returned_count": 0,
                "diagnostics": (unavailable,),
            }
        ),
    )
    store.accept_totals(
        ProjectTotals(
            context=source.context,
            kind="pull-requests",
            open_count=None,
            closed_count=None,
            status="unavailable",
            attempted_at=BEFORE,
            last_good_at=None,
            diagnostics=(unavailable,),
        )
    )
    shown = [entry.diagnostic for entry in store.diagnostics()]
    assert shown.count(unavailable) == 1
