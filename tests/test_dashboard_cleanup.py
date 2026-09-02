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
from textual.widgets import Button, Checkbox, Footer, SelectionList, Static
from textual.widgets._footer import FooterKey

import factories
from app_harness import (
    SequenceCollector,
    footer_keys,
    issue,
    with_first_project,
    with_first_project_snapshot,
    workspace_snapshot,
)
from dashpot.app import DashpotApp
from dashpot.cleanup import (
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
from dashpot.cleanup_view import CleanupReportScreen, CleanupScreen
from dashpot.fetch import FetchReport
from dashpot.issue_list import row_key
from dashpot.legend import LegendScreen
from dashpot.list_pane import ListPane
from dashpot.model import Branch, WorkspaceSnapshot
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


def toasts(app: DashpotApp) -> list[str]:
    return [notification.message for notification in app._notifications]


async def focus_row(app: DashpotApp, pilot: object, pane_id: str, key: str) -> None:
    """Focus a list pane and put its cursor on the row with ``key``."""
    pane = app.query_one(f"#{pane_id}", ListPane)
    pane.table.focus()
    pane.table.move_cursor(row=pane.table.get_row_index(key), animate=False)
    await app.workers.wait_for_complete()


def cleanup_screen(app: DashpotApp) -> CleanupScreen:
    assert isinstance(app.screen, CleanupScreen)
    return app.screen


def confirm_button(app: DashpotApp) -> Button:
    return cleanup_screen(app).query_one("#cleanup-confirm", Button)


def marks(targets: SelectionList[str]) -> list[str]:
    """Read the selection mark rendered in front of each target."""
    return [
        targets.render_line(index).text[:3] for index in range(targets.option_count)
    ]


def problem_text(app: DashpotApp) -> str:
    return str(cleanup_screen(app).query_one("#cleanup-problem", Static).render())


BRANCH_KEY = row_key("branch", PROJECT, "feat")
WORKTREE_KEY = row_key("worktree", PROJECT, WORKTREE)


@pytest.mark.asyncio
async def test_x_on_a_branch_row_previews_selects_performs_and_reports() -> None:
    cleaner = FakeCleaner(
        BRANCH_PREVIEW, reports=[report(BRANCH_PREVIEW, deleted(LOCAL))]
    )
    collector = SequenceCollector(BEFORE, AFTER)
    app = DashpotApp(collector, refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)

        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        assert cleaner.requests == [BRANCH_REQUEST]
        assert cleaner.protected == [(Path.cwd().resolve(), Path(ANCHOR))]
        assert app.cleaning == {PROJECT: "feat"}
        screen = cleanup_screen(app)
        assert str(screen.query_one("#cleanup-title", Static).render()) == (
            "DELETE BRANCH  feat"
        )
        targets = screen.query_one("#cleanup-targets", SelectionList)
        assert targets.option_count == 2
        assert targets.get_option(REMOTE.identity).disabled is True
        assert targets.get_option(LOCAL.identity).disabled is False
        assert "unavailable" in str(targets.get_option(REMOTE.identity).prompt)
        assert confirm_button(app).variant == "default"
        assert problem_text(app) == "Select at least one target."
        # Every target starts unselected, and the mark alone says so: no X
        # until space selects, as in the column editor.
        assert marks(targets) == ["▐ ▌", "▐ ▌"]

        # The highlighted option is the available one; space selects it.
        await pilot.press("space")
        await pilot.pause()
        assert screen.selected() == (LOCAL.identity,)
        assert confirm_button(app).variant == "error"
        assert problem_text(app) == ""
        assert marks(targets) == ["▐X▌", "▐ ▌"]

        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))
        await pilot.pause()

        assert cleaner.confirmations == [
            CleanupConfirmation(BRANCH_REQUEST, "0123456789abcdef", (LOCAL.identity,))
        ]
        text = str(app.screen.query_one("#cleanup-report", Static).render())
        assert "deleted        Local Branch refs/heads/feat" in text
        assert f"recover: git branch feat {TIP}" in text
        assert toasts(app) == ["Test Repository: deleted Local Branch"]
        assert app.cleaning == {}
        # What the deletion changed is observed passively afterwards.
        await wait_until(lambda: app.store.revision == 2)
        assert collector.calls == 2

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CleanupReportScreen)
        assert sorted(row.name for row in app.store.query_branches().rows) == ["main"]
        # The deleted row's neighbour holds the cursor, so the next x is one press away.
        pane = app.query_one("#branches-pane", ListPane)
        assert pane.highlighted() == (row_key("branch", PROJECT, "main"), 0)


@pytest.mark.asyncio
async def test_an_unavailable_target_can_never_stay_selected() -> None:
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = DashpotApp(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        targets = cleanup_screen(app).query_one("#cleanup-targets", SelectionList)
        targets.select(REMOTE.identity)
        await pilot.pause()

        assert cleanup_screen(app).selected() == ()
        assert confirm_button(app).variant == "default"


@pytest.mark.asyncio
async def test_escape_cancels_and_performs_nothing() -> None:
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    collector = SequenceCollector(BEFORE)
    app = DashpotApp(collector, refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.press("space")
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, CleanupScreen)
        assert cleaner.confirmations == []
        assert app.cleaning == {}
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
    app = DashpotApp(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
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
        assert app.cleaning == {PROJECT: "feat"}
        help_text = str(cleanup_screen(app).query_one("#cleanup-help", Static).render())
        assert help_text.startswith("The observed state changed since the preview")
        assert cleanup_screen(app).preview.fingerprint == "fedcba9876543210"
        assert cleanup_screen(app).selected() == ()
        assert toasts(app)[-1].startswith(
            "Test Repository: the observed state changed since the preview"
        )

        await pilot.press("space")
        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))
        assert cleaner.confirmations[1].fingerprint == "fedcba9876543210"
        assert app.cleaning == {}


@pytest.mark.asyncio
async def test_a_worktree_needs_its_acknowledgement_and_carries_its_branch() -> None:
    cleaner = FakeCleaner(
        WORKTREE_PREVIEW,
        reports=[report(WORKTREE_PREVIEW, deleted(TREE), deleted(ATTACHED))],
    )
    app = DashpotApp(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "worktrees-pane", WORKTREE_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        assert cleaner.requests == [WORKTREE_REQUEST]
        screen = cleanup_screen(app)
        assert str(screen.query_one("#cleanup-title", Static).render()) == (
            f"REMOVE WORKTREE  {WORKTREE}"
        )
        targets = screen.query_one("#cleanup-targets", SelectionList)
        details = str(screen.query_one("#cleanup-details", Static).render())
        assert "Local Branch\n  ⊆ every commit" in details
        assert "  only together with Worktree" in details
        acknowledgement = screen.query_one("#cleanup-ignored", Checkbox)
        assert str(acknowledgement.label) == (
            "Delete the 2 ignored path(s) inside it too: .venv/, .dashpot/state/"
        )
        assert acknowledgement.render().plain.startswith("▐ ▌")

        # The Branch alone: it stays checked out until the Worktree goes.
        targets.select(ATTACHED.identity)
        await pilot.pause()
        assert confirm_button(app).variant == "default"
        assert problem_text(app) == (
            "Local Branch can only be deleted together with Worktree."
        )

        targets.select(TREE.identity)
        await pilot.pause()
        assert confirm_button(app).variant == "default"
        assert problem_text(app) == (
            "Acknowledge that the 2 ignored path(s) are deleted with the Worktree."
        )

        acknowledgement.value = True
        await pilot.pause()
        assert confirm_button(app).variant == "error"
        assert acknowledgement.render().plain.startswith("▐X▌")

        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))
        assert cleaner.confirmations == [
            CleanupConfirmation(
                WORKTREE_REQUEST,
                "0123456789abcdef",
                (TREE.identity, ATTACHED.identity),
                delete_ignored=True,
            )
        ]
        assert toasts(app) == [
            "Test Repository: deleted Worktree; deleted Local Branch"
        ]


@pytest.mark.asyncio
async def test_x_is_refused_where_no_deletable_row_has_focus() -> None:
    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = DashpotApp(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()

        assert toasts(app) == ["Highlight a Branch or a Worktree to delete"]
        assert cleaner.requests == []
        assert not isinstance(app.screen, CleanupScreen)


@pytest.mark.asyncio
async def test_a_view_without_a_cleaner_refuses_the_key() -> None:
    app = DashpotApp(SequenceCollector(BEFORE), refresh_seconds=0)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await pilot.pause()

        assert toasts(app) == ["Deleting is not available in this view"]


@pytest.mark.asyncio
async def test_an_inspection_failure_is_a_toast_and_releases_the_project() -> None:
    cleaner = FakeCleaner(OSError("git vanished"))
    app = DashpotApp(SequenceCollector(BEFORE), refresh_seconds=0, cleaner=cleaner)

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
        await pilot.press("x")
        await wait_until(lambda: bool(toasts(app)))
        await pilot.pause()

        assert toasts(app) == ["Test Repository: git vanished"]
        assert app.cleaning == {}
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

    app = DashpotApp(
        SequenceCollector(BEFORE, AFTER),
        refresh_seconds=0,
        fetcher=fetcher,
        cleaner=cleaner,
    )

    try:
        async with app.run_test(size=(140, 50)) as pilot:
            await wait_until(lambda: app.store.revision == 1)
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
            await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))
            await pilot.press("escape")
            await wait_until(lambda: app.store.revision == 2)
    finally:
        cleaner.release.set()


@pytest.mark.asyncio
async def test_a_fetch_in_flight_refuses_the_key() -> None:
    hold = Event()

    def fetcher(anchor: Path) -> FetchReport:
        hold.wait(timeout=2)
        raise OSError("stopped")

    cleaner = FakeCleaner(BRANCH_PREVIEW)
    app = DashpotApp(
        SequenceCollector(BEFORE),
        refresh_seconds=0,
        fetcher=fetcher,
        cleaner=cleaner,
    )

    try:
        async with app.run_test(size=(140, 50)) as pilot:
            await wait_until(lambda: app.store.revision == 1)
            await focus_row(app, pilot, "branches-pane", BRANCH_KEY)
            await pilot.press("f")
            await wait_until(lambda: bool(app.fetching))
            await pilot.press("x")
            await pilot.pause()

            assert toasts(app) == ["Fetching Test Repository; delete after it finishes"]
            assert cleaner.requests == []
            hold.set()
            await wait_until(lambda: not app.fetching)
    finally:
        hold.set()


@pytest.mark.asyncio
async def test_x_is_listed_in_the_footer_and_the_legend() -> None:
    app = DashpotApp(
        SequenceCollector(BEFORE), refresh_seconds=0, cleaner=FakeCleaner()
    )

    async with app.run_test(size=(160, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await pilot.pause()

        assert "x" in footer_keys(app)
        footer = app.query_one(Footer)
        assert ("x", "Delete Branch/Worktree") in [
            (key.key, key.description) for key in footer.query(FooterKey)
        ]

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, LegendScreen)
        assert "Delete Branch/Worktree" in str(
            app.screen.query_one("#legend-keys", Static).render()
        )


@pytest.mark.asyncio
async def test_the_keyboard_alone_reaches_delete_in_a_small_terminal() -> None:
    """At 80x24 the reason and the buttons stay in view, and Tab reaches Delete."""
    cleaner = FakeCleaner(
        WORKTREE_PREVIEW,
        reports=[report(WORKTREE_PREVIEW, deleted(TREE), deleted(ATTACHED))],
    )
    app = DashpotApp(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(80, 24)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "worktrees-pane", WORKTREE_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        # The list has focus, and the reason and the buttons are on screen
        # however much the preview above them scrolls.
        assert app.focused is not None
        assert app.focused.id == "cleanup-targets"
        for selector in ("#cleanup-problem", "#cleanup-cancel", "#cleanup-confirm"):
            region = app.screen.query_one(selector).region
            assert region.right <= 80 and region.bottom <= 24, selector
        assert problem_text(app) == "Select at least one target."

        await pilot.press("space", "down", "space")  # the Worktree, then its Branch
        await pilot.pause()
        assert problem_text(app) == (
            "Acknowledge that the 2 ignored path(s) are deleted with the Worktree."
        )
        await pilot.press("tab")
        assert app.focused.id == "cleanup-ignored"
        await pilot.press("space")
        await pilot.pause()
        assert confirm_button(app).variant == "error"
        assert problem_text(app) == ""

        await pilot.press("tab", "tab")  # Cancel, then Delete selected
        assert app.focused.id == "cleanup-confirm"
        await pilot.press("enter")
        await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))
        assert cleaner.confirmations == [
            CleanupConfirmation(
                WORKTREE_REQUEST,
                "0123456789abcdef",
                (TREE.identity, ATTACHED.identity),
                delete_ignored=True,
            )
        ]


@pytest.mark.asyncio
async def test_pressing_delete_too_early_explains_and_focuses_what_is_missing() -> None:
    """The button always answers: a premature press deletes nothing and says why."""
    cleaner = FakeCleaner(
        WORKTREE_PREVIEW,
        reports=[report(WORKTREE_PREVIEW, deleted(TREE), deleted(ATTACHED))],
    )
    app = DashpotApp(
        SequenceCollector(BEFORE, AFTER), refresh_seconds=0, cleaner=cleaner
    )

    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(lambda: app.store.revision == 1)
        await focus_row(app, pilot, "worktrees-pane", WORKTREE_KEY)
        await pilot.press("x")
        await wait_until(lambda: isinstance(app.screen, CleanupScreen))
        await pilot.pause()

        assert confirm_button(app).disabled is False
        await pilot.click("#cleanup-confirm")
        await pilot.pause()
        assert isinstance(app.screen, CleanupScreen)
        assert cleaner.confirmations == []
        assert toasts(app) == ["Select at least one target."]
        assert app.focused is not None
        assert app.focused.id == "cleanup-targets"

        await pilot.press("space", "down", "space")
        await pilot.click("#cleanup-confirm")
        await pilot.pause()
        assert cleaner.confirmations == []
        assert toasts(app)[-1] == (
            "Acknowledge that the 2 ignored path(s) are deleted with the Worktree."
        )
        assert app.focused.id == "cleanup-ignored"

        await pilot.press("space")
        await pilot.pause()
        assert confirm_button(app).variant == "error"
        await pilot.click("#cleanup-confirm")
        await wait_until(lambda: isinstance(app.screen, CleanupReportScreen))
        assert cleaner.confirmations == [
            CleanupConfirmation(
                WORKTREE_REQUEST,
                "0123456789abcdef",
                (TREE.identity, ATTACHED.identity),
                delete_ignored=True,
            )
        ]
