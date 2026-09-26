"""The ``x`` key: preview, select, confirm, and report a Cleanup on the dashboard.

Observation stays passive; a Cleanup runs only on the key, only after a
person selects targets from the preview and confirms, and its result is
observed the passive way afterwards ([ADR 0019]).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from threading import Event
from typing import Literal

import pytest
from textual.pilot import Pilot
from textual.widgets import Button, Collapsible, Footer, Static
from textual.widgets._footer import FooterKey

import factories
from app_harness import (
    SequenceCollector,
    dashboard_app,
    first_load_landed,
    footer_keys,
    issue,
    legend_keys_text,
    toast_titles,
    toasts,
    with_first_project,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.core.model import Branch, WorkspaceSnapshot
from dashpot.observation.issue_list import row_key
from dashpot.repository.cleanup import (
    BranchCleanupRequest,
    CleanupBlocker,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    CleanupTarget,
    IntegrationFact,
    TargetKind,
    TargetResult,
    WorktreeCleanupRequest,
)
from dashpot.repository.fetch import FetchReport
from dashpot.ui.app import DashpotApp
from dashpot.ui.cleanup_view import (
    FETCH_HINT,
    CleanupReportScreen,
    CleanupScreen,
    blocker_summary,
)
from dashpot.ui.legend import LegendScreen
from dashpot.ui.list_pane import ListPane
from helpers import wait_until

ANCHOR = "/repo"
WORKTREE = "/repo.worktrees/feat"
PROJECT = "project:test-repo"
TIP = "8836fb3000000000000000000000000000000000"


def local(name: str) -> Branch:
    return Branch(
        refname=f"refs/heads/{name}",
        name=name,
        remote=None,
        head=TIP,
        committed_at="2026-08-25T00:00:00Z",
        upstream=f"origin/{name}",
    )


def remote(name: str) -> Branch:
    return Branch(
        refname=f"refs/remotes/origin/{name}",
        name=name,
        remote="origin",
        head=TIP,
        committed_at="2026-08-25T00:00:00Z",
    )


def observed(*branches: Branch, linked: bool = True) -> WorkspaceSnapshot:
    targets = [factories.target(ANCHOR)]
    if linked:
        targets.append(factories.target(WORKTREE, role="linked", branch="feat"))
    snapshot = with_first_project_snapshot(
        workspace_snapshot(issue("test/repo#1", "First")),
        branches=list(branches),
        observation_targets=tuple(targets),
        integration_ref="refs/remotes/origin/main",
        branch_anchor=ANCHOR,
    )
    return with_first_project(snapshot, anchors=(ANCHOR,), primary_anchor=ANCHOR)


BEFORE = observed(local("main"), remote("main"), local("feat"), remote("feat"))
AFTER = observed(local("main"), remote("main"), linked=False)

BRANCH_REQUEST = BranchCleanupRequest(Path(ANCHOR), "feat")
WORKTREE_REQUEST = WorktreeCleanupRequest(Path(ANCHOR), Path(WORKTREE))
INTEGRATED = IntegrationFact(
    integration_ref="refs/remotes/origin/main",
    unintegrated_commits=0,
    content_integrated=None,
)


def target(
    kind: TargetKind,
    identity: str,
    label: str,
    *,
    ref: str | None = None,
    path: str | None = None,
    remote_name: str | None = None,
    requires: str | None = None,
    blockers: tuple[CleanupBlocker, ...] = (),
    consequences: tuple[str, ...] = (),
) -> CleanupTarget:
    return CleanupTarget(
        identity=identity,
        kind=kind,
        label=label,
        expected=TIP,
        ref=ref,
        remote=remote_name,
        path=path,
        integration=INTEGRATED if kind != "worktree" else None,
        observed_at=None,
        requires=requires,
        blockers=blockers,
        consequences=consequences,
    )


LOCAL = target(
    "local-branch",
    "local:refs/heads/feat",
    "Local Branch",
    ref="refs/heads/feat",
    consequences=(f"deletes refs/heads/feat at {TIP[:7]}",),
)
REMOTE = target(
    "remote-branch",
    "remote:origin:refs/heads/feat",
    "Branch at origin",
    ref="refs/remotes/origin/feat",
    remote_name="origin",
    blockers=(
        CleanupBlocker(
            kind="unintegrated",
            detail="2 commit(s) not reachable from refs/remotes/origin/main",
        ),
    ),
)
TREE = target(
    "worktree",
    f"worktree:{WORKTREE}",
    "Worktree",
    path=WORKTREE,
    consequences=(f"removes {WORKTREE} with git worktree remove",),
)
ATTACHED = target(
    "local-branch",
    "local:refs/heads/feat",
    "Local Branch",
    ref="refs/heads/feat",
    requires=TREE.identity,
)


def preview(
    kind: Literal["branch", "worktree"],
    subject: str,
    *targets: CleanupTarget,
    ignored: tuple[str, ...] = (),
    fingerprint: str = "0123456789abcdef",
) -> CleanupPreview:
    return CleanupPreview(
        kind=kind,
        subject=subject,
        anchor=ANCHOR,
        targets=targets,
        ignored=ignored,
        refusals=(),
        fingerprint=fingerprint,
    )


BRANCH_PREVIEW = preview("branch", "feat", LOCAL, REMOTE)
WORKTREE_PREVIEW = preview(
    "worktree", WORKTREE, TREE, ATTACHED, ignored=(".venv/", ".dashpot/state/")
)


def report(
    shown: CleanupPreview,
    *results: TargetResult,
    changed: bool = False,
    refusals: tuple[str, ...] = (),
) -> CleanupReport:
    return CleanupReport(
        kind=shown.kind,
        subject=shown.subject,
        anchor=shown.anchor,
        dry_run=False,
        performed=not changed and not refusals,
        preview=shown,
        changed=changed,
        refusals=refusals,
        results=results,
    )


def deleted(one: CleanupTarget) -> TargetResult:
    return TargetResult(
        identity=one.identity,
        kind=one.kind,
        label=one.label,
        expected=one.expected,
        outcome="deleted",
        detail=f"deleted {one.label}",
        recovery=f"git branch feat {TIP}",
    )


def refused(one: CleanupTarget) -> TargetResult:
    return TargetResult(
        identity=one.identity,
        kind=one.kind,
        label=one.label,
        expected=one.expected,
        outcome="refused",
        detail=f"{one.label} moved after the preview",
    )


class FakeCleaner:
    """An adapter that answers scripted previews and reports, recording each call."""

    def __init__(
        self, *previews: CleanupPreview | Exception, reports: Sequence[object] = ()
    ) -> None:
        self.previews = list(previews)
        self.reports = list(reports)
        self.requests: list[CleanupRequest] = []
        self.protected: list[tuple[Path, ...]] = []
        self.confirmations: list[CleanupConfirmation] = []
        self.release = Event()
        self.release.set()

    def inspect(
        self, request: CleanupRequest, *, protected: Sequence[Path]
    ) -> CleanupPreview:
        self.requests.append(request)
        self.protected.append(tuple(protected))
        answer = self.previews.pop(0) if self.previews else BRANCH_PREVIEW
        if isinstance(answer, Exception):
            raise answer
        return answer

    def perform(
        self, confirmation: CleanupConfirmation, *, protected: Sequence[Path]
    ) -> CleanupReport:
        self.confirmations.append(confirmation)
        self.release.wait(timeout=2)
        answer = self.reports.pop(0)
        if isinstance(answer, Exception):
            raise answer
        assert isinstance(answer, CleanupReport)
        return answer


async def focus_row(
    app: DashpotApp, pilot: Pilot[None], pane_id: str, key: str
) -> None:
    """Focus a list pane and put its cursor on the row with ``key``."""
    pane = app.query_one(f"#{pane_id}", ListPane)
    pane.table.focus()
    await pilot.pause()
    pane.table.move_cursor(row=pane.table.get_row_index(key), animate=False)
    await app.workers.wait_for_complete()


def cleanup_screen(app: DashpotApp) -> CleanupScreen:
    assert isinstance(app.screen, CleanupScreen)
    return app.screen


def confirm_button(app: DashpotApp) -> Button:
    return cleanup_screen(app).query_one("#cleanup-confirm", Button)


def choices(app):
    return {one.target.identity: one.choice() for one in cleanup_screen(app).targets()}


def marks(targets):
    return [one.render().plain[:3] for one in targets.values()]


def details(app):
    return "\n".join(
        str(one.render())
        for one in cleanup_screen(app).query("#cleanup-targets Static")
    )


def problem_text(app: DashpotApp) -> str:
    return str(cleanup_screen(app).query_one("#cleanup-problem", Static).render())


def callout_text(app: DashpotApp) -> str:
    """The confirmation callout as a person reads it, or "" while it is hidden."""
    callout = cleanup_screen(app).query_one("#cleanup-callout")
    if not callout.display:
        return ""
    return "\n".join(str(one.render()) for one in callout.query(Static))


BRANCH_KEY = row_key("branch", PROJECT, "feat")
WORKTREE_KEY = row_key("worktree", PROJECT, WORKTREE)


@pytest.mark.asyncio
async def test_x_on_a_branch_row_previews_selects_performs_and_notifies() -> None:
    cleaner = FakeCleaner(
        BRANCH_PREVIEW, reports=[report(BRANCH_PREVIEW, deleted(LOCAL))]
    )
    collector = SequenceCollector(BEFORE, AFTER)
    app = dashboard_app(collector, refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)

        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        assert cleaner.requests == [BRANCH_REQUEST]
        assert cleaner.protected == [(Path.cwd().resolve(), Path(ANCHOR))]
        assert app.cleanups.cleaning == {PROJECT: "feat"}
        screen = cleanup_screen(app)
        assert str(screen.query_one("#cleanup-title", Static).render()) == (
            "Delete Branch"
        )
        targets = choices(app)
        assert targets[LOCAL.identity] is None
        assert targets[REMOTE.identity].disabled is True
        assert screen.selected() == (LOCAL.identity,)
        assert confirm_button(app).variant == "error"
        assert problem_text(app) == ""
        assert not screen.query("#cleanup-target-0")
        assert marks({REMOTE.identity: targets[REMOTE.identity]}) == ["▐ ▌"]

        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: app.store.revision == 2)

        assert cleaner.confirmations == [
            CleanupConfirmation(BRANCH_REQUEST, "0123456789abcdef", (LOCAL.identity,))
        ]
        assert toasts(app) == ["Deleted Local Branch"]
        assert toast_titles(app) == ["Test Repository cleanup"]
        assert app.cleanups.cleaning == {}
        assert not isinstance(app.screen, CleanupReportScreen)
        # What the deletion changed is observed passively afterwards.
        assert collector.calls == 2

        assert sorted(row.name for row in app.store.query_branches().rows) == ["main"]
        # The deleted row's neighbour holds the cursor, so the next x is one press away.
        pane = app.query_one("#branches-pane", ListPane)
        assert pane.highlighted() == (row_key("branch", PROJECT, "main"), 0)


@pytest.mark.asyncio
async def test_a_refused_cleanup_keeps_its_detailed_report() -> None:
    cleaner = FakeCleaner(
        BRANCH_PREVIEW, reports=[report(BRANCH_PREVIEW, refused(LOCAL))]
    )
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.press("space")
        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))

        report_text = str(app.screen.query_one("#cleanup-report", Static).render())
        assert "refused        Local Branch refs/heads/feat" in report_text
        assert "Local Branch moved after the preview" in report_text
        assert toasts(app) == ["Refused Local Branch"]
        assert toast_titles(app) == ["Test Repository cleanup"]


@pytest.mark.asyncio
async def test_an_unavailable_target_can_never_stay_selected() -> None:
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        targets = choices(app)
        targets[REMOTE.identity].value = True
        await pilot.pause()

        assert cleanup_screen(app).selected() == (LOCAL.identity,)
        assert confirm_button(app).variant == "error"


@pytest.mark.asyncio
async def test_escape_cancels_and_performs_nothing() -> None:
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    collector = SequenceCollector(BEFORE)
    app = dashboard_app(collector, refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.press("space")
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, CleanupScreen)
        assert cleaner.confirmations == []
        assert app.cleanups.cleaning == {}
        assert collector.calls == 1
        assert toasts(app) == []


@pytest.mark.asyncio
async def test_a_changed_preview_reopens_for_another_confirmation() -> None:
    revised = preview("branch", "feat", LOCAL, fingerprint="fedcba9876543210")
    cleaner = FakeCleaner(
        BRANCH_PREVIEW,
        reports=[
            report(
                BRANCH_PREVIEW,
                changed=True,
                refusals=(
                    "the observed state changed since the preview; confirm again "
                    "against the revised preview",
                ),
            ).model_copy(update={"preview": revised}),
            report(revised, deleted(LOCAL)),
        ],
    )
    app = dashboard_app(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.press("space")
        await pilot.click("#cleanup-confirm")
        await wait_until(
            lambda: isinstance(app.screen, CleanupScreen) and app.screen.changed
        )
        await pilot.pause()

        # Nothing was performed; the revised preview asks again, and the
        # Project stays held meanwhile.
        assert len(cleaner.confirmations) == 1
        assert app.cleanups.cleaning == {PROJECT: "feat"}
        help_text = str(cleanup_screen(app).query_one("#cleanup-help", Static).render())
        assert help_text.startswith("The observed state changed since the preview")
        assert cleanup_screen(app).preview.fingerprint == "fedcba9876543210"
        assert cleanup_screen(app).selected() == (LOCAL.identity,)
        assert toasts(app)[-1].startswith(
            "Test Repository: the observed state changed since the preview"
        )

        await pilot.press("space")
        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: app.cleanups.cleaning == {})
        assert cleaner.confirmations[1].fingerprint == "fedcba9876543210"
        assert toasts(app)[-1] == "Deleted Local Branch"
        assert not isinstance(app.screen, CleanupReportScreen)


@pytest.mark.asyncio
async def test_a_worktree_starts_with_its_branch_and_discloses_ignored_content() -> (
    None
):
    cleaner = FakeCleaner(
        WORKTREE_PREVIEW,
        reports=[report(WORKTREE_PREVIEW, deleted(TREE), deleted(ATTACHED))],
    )
    app = dashboard_app(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "worktrees-pane", WORKTREE_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        assert cleaner.requests == [WORKTREE_REQUEST]
        screen = cleanup_screen(app)
        assert str(screen.query_one("#cleanup-title", Static).render()) == (
            "Remove Worktree"
        )
        targets = choices(app)
        shown = details(app)
        assert "Commits integrated into origin/main." in shown
        assert "Requires removing Worktree." in shown
        assert "Includes 2 ignored paths and their contents." in shown
        # No tick stands between a person and the ignored content: the
        # dialog discloses it instead.
        assert not screen.query("#cleanup-ignored")

        # The Branch is additional to the fixed Worktree subject, and a
        # Worktree and its Branch are normally finished together.
        assert targets[TREE.identity] is None
        assert marks({ATTACHED.identity: targets[ATTACHED.identity]}) == ["▐X▌"]
        assert screen.selected() == (TREE.identity, ATTACHED.identity)
        assert problem_text(app) == ""
        assert confirm_button(app).variant == "error"
        assert str(confirm_button(app).label) == "Remove Worktree"
        assert callout_text(app) == (
            f"Confirming will:\nremove Worktree {WORKTREE}\n"
            "  with 2 ignored paths and their contents: .venv/, .dashpot/state/\n"
            "delete local Branch feat"
        )

        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: app.cleanups.cleaning == {})
        assert cleaner.confirmations == [
            CleanupConfirmation(
                WORKTREE_REQUEST,
                "0123456789abcdef",
                (TREE.identity, ATTACHED.identity),
                delete_ignored=True,
            )
        ]
        assert toasts(app) == ["Removed Worktree\nDeleted Local Branch"]
        assert not isinstance(app.screen, CleanupReportScreen)


BLOCKED_TREE = target(
    "worktree",
    f"worktree:{WORKTREE}",
    "Worktree",
    path=WORKTREE,
    blockers=(CleanupBlocker(kind="dirty", detail="1 changed path"),),
)
HELD = target(
    "local-branch",
    "local:refs/heads/feat",
    "Local Branch",
    ref="refs/heads/feat",
    requires=BLOCKED_TREE.identity,
    blockers=(
        CleanupBlocker(
            kind="checked-out",
            detail=f"checked out at {WORKTREE}, whose removal is blocked",
        ),
    ),
)
BLOCKED_WORKTREE_PREVIEW = preview("worktree", WORKTREE, BLOCKED_TREE, HELD)


@pytest.mark.asyncio
async def test_a_blocked_worktree_holds_its_branch_unavailable() -> None:
    cleaner = FakeCleaner(BLOCKED_WORKTREE_PREVIEW)
    app = dashboard_app(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "worktrees-pane", WORKTREE_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        screen = cleanup_screen(app)
        targets = choices(app)
        assert len(targets) == 2
        assert targets[BLOCKED_TREE.identity] is None
        assert targets[HELD.identity].disabled is True
        shown = details(app)
        assert "1 changed path" in shown
        assert (
            f"Blocked: checked out at {WORKTREE}, whose removal is blocked"
        ) in shown
        assert problem_text(app) == "Nothing here can be deleted."
        assert not screen.query("#cleanup-confirm")
        assert app.focused is not None
        assert app.focused.id == "cleanup-cancel"
        assert marks({HELD.identity: targets[HELD.identity]}) == ["▐ ▌"]
        assert cleaner.confirmations == []
        await pilot.press("enter")
        await wait_until(lambda: not isinstance(app.screen, CleanupScreen))
        assert app.cleanups.cleaning == {}


@pytest.mark.asyncio
async def test_x_is_refused_where_no_deletable_row_has_focus() -> None:
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()

        assert toasts(app) == ["Highlight a Branch or a Worktree to delete"]
        assert cleaner.requests == []
        assert not isinstance(app.screen, CleanupScreen)


@pytest.mark.asyncio
async def test_a_view_without_a_cleaner_refuses_the_key() -> None:
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await pilot.pause()

        assert toasts(app) == ["Deleting is not available in this view"]


@pytest.mark.asyncio
async def test_an_inspection_failure_is_a_toast_and_releases_the_project() -> None:
    cleaner = FakeCleaner(OSError("git vanished"))
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: bool(toasts(app)))
        await pilot.pause()

        assert toasts(app) == ["Test Repository: git vanished"]
        assert app.cleanups.cleaning == {}
        assert not isinstance(app.screen, CleanupScreen)


@pytest.mark.asyncio
async def test_cleanup_and_fetch_exclude_each_other_per_project() -> None:
    cleaner = FakeCleaner(
        BRANCH_PREVIEW, reports=[report(BRANCH_PREVIEW, deleted(LOCAL))]
    )
    cleaner.release.clear()
    fetched = Event()

    def fetcher(anchor: Path) -> FetchReport:
        fetched.set()
        raise AssertionError("never fetched")

    app = dashboard_app(
        SequenceCollector(BEFORE, AFTER),
        refresh_seconds=0,
        fetcher=fetcher,
        cleaner=cleaner,
    )

    try:
        async with app.run_test(size=(140, 50)) as pilot:
            await wait_until(lambda: first_load_landed(app))
            await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
            await pilot.press("x")
            await wait_until(lambda: isinstance(app.screen, CleanupScreen))
            await pilot.press("space")
            await pilot.click("#cleanup-confirm")
            await wait_until(lambda: len(cleaner.confirmations) == 1)
            await pilot.pause()

            # The perform is in flight: a fetch of the same Project is refused.
            await pilot.press("f")
            await pilot.pause()
            assert toasts(app) == [
                "Cleaning up Test Repository; fetch after it finishes"
            ]
            assert not fetched.is_set()

            cleaner.release.set()
            await wait_until(lambda: app.store.revision == 2)
            assert not isinstance(app.screen, CleanupReportScreen)
    finally:
        cleaner.release.set()


@pytest.mark.asyncio
async def test_a_fetch_in_flight_refuses_the_key() -> None:
    hold = Event()

    def fetcher(anchor: Path) -> FetchReport:
        hold.wait(timeout=2)
        raise OSError("stopped")

    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = dashboard_app(
        SequenceCollector(BEFORE),
        refresh_seconds=0,
        fetcher=fetcher,
        cleaner=cleaner,
    )

    try:
        async with app.run_test(size=(140, 50)) as pilot:
            await wait_until(lambda: first_load_landed(app))
            await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
            await pilot.press("f")
            await wait_until(lambda: bool(app.fetches.fetching))
            await pilot.press("x")
            await pilot.pause()

            assert toasts(app) == ["Fetching Test Repository; delete after it finishes"]
            assert cleaner.requests == []
            hold.set()
            await wait_until(lambda: not app.fetches.fetching)
    finally:
        hold.set()


@pytest.mark.asyncio
async def test_x_is_listed_in_the_footer_and_the_legend() -> None:
    app = dashboard_app(
        SequenceCollector(BEFORE), refresh_seconds=0, cleaner=FakeCleaner()
    )

    async with app.run_test(size=(160, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await pilot.pause()

        assert "x" in footer_keys(app)
        # The Footer recomposes its keys after the bindings settle, so wait
        # for the entry rather than for one pause.
        footer = app.query_one(Footer)
        await wait_until(
            lambda: (
                ("x", "Delete Branch/Worktree")
                in [(key.key, key.description) for key in footer.query(FooterKey)]
            )
        )

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, LegendScreen)
        assert "Delete Branch/Worktree" in legend_keys_text(app)


@pytest.mark.asyncio
async def test_the_keyboard_alone_reaches_delete_in_a_small_terminal() -> None:
    """At 80x24 the reason and the buttons stay in view, and Tab reaches Delete."""
    cleaner = FakeCleaner(
        WORKTREE_PREVIEW,
        reports=[report(WORKTREE_PREVIEW, deleted(TREE), deleted(ATTACHED))],
    )
    app = dashboard_app(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "worktrees-pane", WORKTREE_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        # The first choice has focus, never the button, so a stray Enter
        # after x confirms nothing; the reason and the buttons are on screen
        # however much the preview above them scrolls.
        assert app.focused is not None
        assert app.focused.id == "cleanup-target-1"
        for selector in ("#cleanup-problem", "#cleanup-cancel", "#cleanup-confirm"):
            region = app.screen.query_one(selector).region
            assert region.right <= 80 and region.bottom <= 24, selector
        assert problem_text(app) == ""
        assert confirm_button(app).variant == "error"

        # The evidence disclosure, then Cancel, then the confirm button.
        await pilot.press("tab", "tab", "tab")
        assert app.focused.id == "cleanup-confirm"
        await pilot.press("enter")
        await wait_until(lambda: app.cleanups.cleaning == {})
        assert cleaner.confirmations == [
            CleanupConfirmation(
                WORKTREE_REQUEST,
                "0123456789abcdef",
                (TREE.identity, ATTACHED.identity),
                delete_ignored=True,
            )
        ]
        assert toasts(app) == ["Removed Worktree\nDeleted Local Branch"]
        assert not isinstance(app.screen, CleanupReportScreen)


@pytest.mark.asyncio
async def test_pressing_delete_too_early_explains_and_focuses_what_is_missing() -> None:
    """The button always answers: a premature press deletes nothing and says why."""
    blocked_local = LOCAL.model_copy(
        update={
            "blockers": (
                CleanupBlocker(kind="checked-out", detail="checked out at /elsewhere"),
            )
        }
    )
    available_remote = REMOTE.model_copy(update={"blockers": ()})
    shown = preview("branch", "feat", blocked_local, available_remote)
    cleaner = FakeCleaner(shown, reports=[report(shown, deleted(available_remote))])
    app = dashboard_app(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: first_load_landed(app))
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        # No Branch preview starts with anything selected, and the callout
        # stays hidden while confirming would delete nothing.
        assert cleanup_screen(app).selected() == ()
        assert callout_text(app) == ""
        assert confirm_button(app).disabled is False
        await pilot.click("#cleanup-confirm")
        await pilot.pause()
        assert isinstance(app.screen, CleanupScreen)
        assert cleaner.confirmations == []
        assert toasts(app) == ["Select what to delete."]
        assert app.focused is not None
        assert app.focused.id == "cleanup-target-1"

        await pilot.press("space")
        await pilot.pause()
        assert confirm_button(app).variant == "error"
        assert str(confirm_button(app).label) == "Delete Branch"
        assert callout_text(app) == "Confirming will:\ndelete Branch feat at origin"
        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: app.cleanups.cleaning == {})
        assert cleaner.confirmations == [
            CleanupConfirmation(
                BRANCH_REQUEST, "0123456789abcdef", (available_remote.identity,)
            )
        ]


PUSHED = target(
    "remote-branch",
    "remote:origin:refs/heads/feat",
    "Branch at origin",
    ref="refs/remotes/origin/feat",
    remote_name="origin",
    requires=TREE.identity,
)


@pytest.mark.asyncio
async def test_unticking_a_default_branch_retains_it_and_keeps_the_label():
    shown = preview("worktree", WORKTREE, TREE, ATTACHED, PUSHED, ignored=(".venv/",))
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)
    async with app.run_test(size=(120, 45)) as pilot:
        confirmed: list[CleanupConfirmation | None] = []
        await app.push_screen(
            CleanupScreen(WORKTREE_REQUEST, shown), callback=confirmed.append
        )
        await pilot.pause()
        screen = cleanup_screen(app)
        assert not screen.query("#cleanup-target-0")
        # One grouping label however many Branches follow the Worktree.
        assert [
            str(one.render())
            for one in screen.query(".cleanup-summary")
            if str(one.render()) == "Also remove"
        ] == ["Also remove"]
        assert screen.selected() == (
            TREE.identity,
            ATTACHED.identity,
            PUSHED.identity,
        )
        assert callout_text(app).splitlines()[-2:] == [
            "delete local Branch feat",
            "delete Branch feat at origin",
        ]

        choices(app)[ATTACHED.identity].value = False
        choices(app)[PUSHED.identity].value = False
        await pilot.pause()
        assert screen.selected() == (TREE.identity,)
        assert str(confirm_button(app).label) == "Remove Worktree"
        assert callout_text(app) == (
            f"Confirming will:\nremove Worktree {WORKTREE}\n"
            "  with 1 ignored path and its contents: .venv/"
        )
        await pilot.click("#cleanup-confirm")
        await pilot.pause()
        # Removing the Worktree is itself the acknowledgement of its content.
        assert confirmed == [
            CleanupConfirmation(
                WORKTREE_REQUEST,
                "0123456789abcdef",
                (TREE.identity,),
                delete_ignored=True,
            )
        ]


@pytest.mark.asyncio
async def test_a_remote_branch_away_from_the_local_tip_starts_unticked():
    moved = PUSHED.model_copy(update={"expected": "f" * 40})
    shown = preview("worktree", WORKTREE, TREE, ATTACHED, moved)
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)
    async with app.run_test(size=(120, 45)) as pilot:
        await app.push_screen(CleanupScreen(WORKTREE_REQUEST, shown))
        await pilot.pause()
        screen = cleanup_screen(app)
        assert screen.selected() == (TREE.identity, ATTACHED.identity)
        assert marks(
            {one: choices(app)[one] for one in (ATTACHED.identity, moved.identity)}
        ) == ["▐X▌", "▐ ▌"]


@pytest.mark.asyncio
async def test_a_worktree_without_choices_focuses_the_body_not_the_button():
    shown = preview("worktree", WORKTREE, TREE, ignored=(".venv/",))
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)
    async with app.run_test(size=(120, 45)) as pilot:
        await app.push_screen(CleanupScreen(WORKTREE_REQUEST, shown))
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "cleanup-body"
        assert confirm_button(app).variant == "error"


@pytest.mark.asyncio
async def test_blocked_choices_keep_all_reasons_and_keyboard_access_to_full_evidence():
    long_path = "/projects/" + "nested/" * 20 + "release-candidate"
    blocked = LOCAL.model_copy(
        update={
            "blockers": (
                CleanupBlocker(
                    kind="checked-out", detail=f"checked out at {long_path}"
                ),
                CleanupBlocker(
                    kind="unintegrated",
                    detail="3 unintegrated commits",
                    command="git log origin/main..feat",
                ),
            ),
            "integration": IntegrationFact(
                integration_ref="refs/remotes/origin/main",
                unintegrated_commits=3,
                content_integrated=False,
            ),
            "consequences": ("Recovery: git branch feat " + TIP,),
        }
    )
    shown = preview("branch", "feat", blocked)
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(CleanupScreen(BRANCH_REQUEST, shown))
        await pilot.pause()
        screen = cleanup_screen(app)
        reasons = [str(one.render()) for one in screen.query(".cleanup-blocker")]
        assert "Checked out in a Worktree; remove that Worktree first." in reasons
        # Judged against a Remote-Tracking ref, the block may only be stale.
        assert (
            "3 commits not integrated into origin/main. "
            "If it has since merged, press f to fetch and check again."
        ) in reasons
        assert app.focused is not None
        assert app.focused.id == "cleanup-cancel"
        assert not screen.query("#cleanup-confirm")
        await pilot.press("shift+tab", "enter")
        evidence = screen.query_one("#cleanup-evidence-0", Collapsible)
        assert not evidence.collapsed
        assert long_path in details(app)
        assert "Next step: git log origin/main..feat" in details(app)
        assert "Recovery: git branch feat " + TIP in details(app)
        body = screen.query_one("#cleanup-body")
        body.scroll_end(animate=False)
        content = evidence.query_one("Contents Static", Static)
        # Scrolling is deferred until layout, even with animation disabled.
        await wait_until(lambda: content.region.bottom <= body.region.bottom)
        assert screen.query_one("#cleanup-cancel").region.bottom <= 24
        await pilot.press("escape")
        assert not isinstance(app.screen, CleanupScreen)


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
async def test_long_worktree_identity_and_all_ignored_paths_are_accessible(size):
    long_path = "/projects/worktrees/" + "release-candidate-" * 6
    tree = TREE.model_copy(update={"path": long_path})
    ignored = tuple(f"ignored-{number}/" for number in range(30))
    shown = preview("worktree", long_path, tree, ignored=ignored)
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)
    async with app.run_test(size=size) as pilot:
        await app.push_screen(CleanupScreen(WORKTREE_REQUEST, shown))
        await pilot.pause()
        screen = cleanup_screen(app)
        subject = screen.query_one("#cleanup-subject", Static)
        assert str(subject.render()) == Path(long_path).name
        assert subject.region.height > 1
        assert long_path in details(app)
        paths = screen.query_one("#cleanup-paths", Collapsible)
        for _ in range(12):
            if app.focused is not None and app.focused.parent is paths:
                break
            await pilot.press("tab")
        assert app.focused is not None and app.focused.parent is paths
        await pilot.press("enter")
        assert not paths.collapsed
        inventory = screen.query_one("#cleanup-path-list", Static)
        assert str(inventory.render()).splitlines() == list(ignored)
        body = screen.query_one("#cleanup-body")
        body.scroll_end(animate=False)
        # Scrolling is deferred until layout, even with animation disabled.
        await wait_until(
            lambda: (
                inventory.region.height == len(ignored)
                and inventory.region.bottom <= body.region.bottom
            )
        )
        assert screen.query_one("#cleanup-confirm").region.bottom <= size[1]


@pytest.mark.asyncio
async def test_content_integration_and_changed_preview_keep_consequences_explicit():
    integrated = ATTACHED.model_copy(
        update={
            "integration": IntegrationFact(
                integration_ref="refs/remotes/origin/main",
                unintegrated_commits=3,
                content_integrated=True,
            )
        }
    )
    shown = preview("worktree", WORKTREE, TREE, integrated, ignored=(".venv/",))
    app = dashboard_app(SequenceCollector(BEFORE), refresh_seconds=0)
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(CleanupScreen(WORKTREE_REQUEST, shown, changed=True))
        await pilot.pause()
        screen = cleanup_screen(app)
        text = details(app)
        assert (
            "Content integrated into origin/main; 3 original commits are not retained there."
            in text
        )
        assert "Keeps the local Branch unless selected below." in text
        assert "Includes 1 ignored path and its contents." in text
        assert "Nothing was deleted. Select and confirm again." in str(
            screen.query_one("#cleanup-help", Static).render()
        )
        # A preview reopened because the state changed never re-arms the
        # default Branch choice: the person selects and confirms again.
        assert screen.selected() == (TREE.identity,)
        await pilot.press("space", "down")
        await pilot.pause()
        branch_summary = screen.targets()[1].query_one(".cleanup-summary", Static)
        body = screen.query_one("#cleanup-body")
        assert branch_summary.region.bottom <= body.region.bottom
        assert branch_summary.region.y >= body.region.y


@pytest.mark.parametrize(
    ("kind", "integration_ref", "hinted"),
    [
        ("unintegrated", "refs/remotes/origin/main", True),
        ("unknown-integration", "refs/remotes/origin/main", True),
        # A local Integration Branch is not stale for want of a fetch.
        ("unintegrated", "refs/heads/main", False),
        ("unknown-integration", None, False),
        ("dirty", "refs/remotes/origin/main", False),
    ],
)
def test_only_an_integration_block_against_a_remote_ref_hints_at_fetching(
    kind, integration_ref, hinted
):
    blocker = CleanupBlocker(kind=kind, detail="counted")
    blocked = LOCAL.model_copy(
        update={
            "blockers": (blocker,),
            "integration": IntegrationFact(
                integration_ref=integration_ref,
                unintegrated_commits=2,
                content_integrated=False,
            ),
        }
    )
    assert blocker_summary(blocker, blocked).endswith(FETCH_HINT) is hinted
