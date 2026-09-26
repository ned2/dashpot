"""Present Cleanup choices with their blockers, consequences, and evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, override

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import DescendantFocus
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Footer, Static

from ..repository.cleanup import (
    CHANGED_SINCE_PREVIEW,
    CleanupBlocker,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    CleanupTarget,
    default_choices,
    describe_cleanup_report,
    primary_target,
    retained_choices,
)
from .branch_cells import fetch_age_text
from .marked_widgets import MarkedCheckbox

CHANGED_HELP = (
    f"{CHANGED_SINCE_PREVIEW[0].upper()}{CHANGED_SINCE_PREVIEW[1:]}. "
    "Nothing was deleted. Select and confirm again."
)


def short_ref(ref: str | None) -> str:
    """Label a ref without its Git namespace."""
    return (
        (ref or "the Integration Branch")
        .removeprefix("refs/heads/")
        .removeprefix("refs/remotes/")
    )


FETCH_HINT = "If it has since merged, press f to fetch and check again."

# How many ignored path names the confirmation callout spells out.
CALLOUT_IGNORED_NAMES = 3


def blocker_summary(blocker: CleanupBlocker, target: CleanupTarget) -> str:
    """Keep each blocking condition visible beside its target.

    An integration block judged against a Remote-Tracking ref may only be
    stale: Dashpot never fetches on its own, so a merged Pull Request whose
    commit has not been fetched still reads as unintegrated.
    """
    summary = _blocker_text(blocker, target)
    fact = target.integration
    if (
        blocker.kind in {"unintegrated", "unknown-integration"}
        and fact is not None
        and (fact.integration_ref or "").startswith("refs/remotes/")
    ):
        return f"{summary} {FETCH_HINT}"
    return summary


def _blocker_text(blocker: CleanupBlocker, target: CleanupTarget) -> str:
    if blocker.kind == "checked-out":
        return (
            "Worktree removal is blocked; this Branch stays checked out."
            if target.requires
            else "Checked out in a Worktree; remove that Worktree first."
        )
    if blocker.kind == "unintegrated" and target.integration:
        fact = target.integration
        return (
            f"{fact.unintegrated_commits} commits not integrated into "
            f"{short_ref(fact.integration_ref)}."
        )
    summaries = {
        "dirty": "Uncommitted changes or untracked files; inspect before removal.",
        "locked": "The Worktree is locked; inspect the lock before removal.",
        "agent-session": "An Agent Session is still recorded; exit it or verify its liveness.",
        "agent-run": "Active Issue work remains; finish it before removal.",
        "work-store": "The Work Store cannot be verified; inspect it before removal.",
        "protected": "This Worktree is in use by Dashpot or configured as a Repository Anchor.",
        "main-worktree": "The main Worktree cannot be removed.",
    }
    return summaries.get(blocker.kind, blocker.detail)


def ignored_description(preview: CleanupPreview) -> str:
    """Describe ignored paths as including their contents."""
    count = len(preview.ignored)
    return (
        "1 ignored path and its contents"
        if count == 1
        else f"{count} ignored paths and their contents"
    )


def target_summary(preview: CleanupPreview, target: CleanupTarget) -> str:
    """Show the consequences needed to choose a Cleanup target."""
    lines: list[str] = []
    if target.kind == "worktree":
        lines.append("Removes the directory and its contents.")
        if any(one.requires == target.identity for one in preview.targets):
            lines.append("Keeps the local Branch unless selected below.")
        if preview.ignored:
            lines.append(f"Includes {ignored_description(preview)}.")
    else:
        fact = target.integration
        if fact and fact.state == "integrated":
            lines.append(f"Commits integrated into {short_ref(fact.integration_ref)}.")
        elif fact and fact.state == "content-integrated":
            lines.append(
                f"Content integrated into {short_ref(fact.integration_ref)}; "
                f"{fact.unintegrated_commits} original commits are not retained there."
            )
        if target.requires:
            required = preview.target(target.requires)
            lines.append(
                f"Requires removing {required.label if required else 'the Worktree'}."
            )
        if target.kind == "remote-branch":
            lines.append(
                f"Deletes the Branch on {target.remote}; refuses if its tip changed."
            )
    return "\n".join(lines)


def target_evidence(target: CleanupTarget) -> str:
    """Retain full target identity, recovery commands, and blocker evidence."""
    lines = [f"{target.path or target.ref}", f"Commit: {target.expected}"]
    if target.observed_at:
        lines.append(
            f"Repository fetch timestamp: {target.observed_at} (not per-remote verification)"
        )
    for blocker in target.blockers:
        lines.append(f"Blocked: {blocker.detail}")
        if blocker.command:
            lines.append(f"Next step: {blocker.command}")
    lines.extend(target.consequences)
    return "\n".join(lines)


def confirmation_lines(preview: CleanupPreview, selected: Sequence[str]) -> list[str]:
    """State what confirming the selection removes and deletes, one target a line.

    The confirm button's label never changes, so this recap is where the
    selection is read before confirming: every selected target, and the
    ignored content a Worktree takes with it.
    """
    lines: list[str] = []
    for target in preview.targets:
        if target.identity not in selected:
            continue
        name = short_ref(target.ref)
        if target.kind == "worktree":
            lines.append(f"remove Worktree {target.path}")
            if preview.ignored:
                names = ", ".join(preview.ignored[:CALLOUT_IGNORED_NAMES])
                more = ", …" if len(preview.ignored) > CALLOUT_IGNORED_NAMES else ""
                lines.append(f"  with {ignored_description(preview)}: {names}{more}")
        elif target.kind == "local-branch":
            lines.append(f"delete local Branch {name}")
        else:
            name = name.removeprefix(f"{target.remote}/")
            lines.append(f"delete Branch {name} at {target.remote}")
    return lines


class CleanupChoice(MarkedCheckbox):
    """Move between Cleanup choices without traversing their evidence."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("down", "next_choice(1)", show=False),
        Binding("up", "next_choice(-1)", show=False),
    ]

    def action_next_choice(self, step: int) -> None:
        choices = [one for one in self.screen.query(CleanupChoice) if not one.disabled]
        if self in choices:
            choices[(choices.index(self) + step) % len(choices)].focus()


class CleanupTargetView(Vertical):
    """Group one Cleanup choice with its availability and consequences."""

    def __init__(
        self,
        preview: CleanupPreview,
        target: CleanupTarget,
        index: int,
        *,
        primary: bool = False,
        chosen: bool = False,
        unverified_remote: bool = False,
    ) -> None:
        super().__init__(classes="cleanup-target")
        self.preview = preview
        self.target = target
        self.index = index
        self.primary = primary
        self.chosen = chosen
        self.unverified_remote = unverified_remote

    @override
    def compose(self) -> ComposeResult:
        target = self.target
        with Horizontal(classes="cleanup-target-heading"):
            if self.primary:
                yield Static(target.label, markup=False, classes="cleanup-primary")
            else:
                yield CleanupChoice(
                    target.label,
                    self.chosen and target.available,
                    id=f"cleanup-target-{self.index}",
                    disabled=not target.available,
                )
            yield Static(
                "AVAILABLE" if target.available else "BLOCKED",
                classes="cleanup-availability"
                + (" -blocked" if not target.available else ""),
            )
        for blocker in target.blockers:
            yield Static(
                blocker_summary(blocker, target),
                markup=False,
                classes="cleanup-blocker",
            )
        if self.unverified_remote:
            yield Static(
                f"The latest fetch did not verify {target.remote}; these are retained Remote-Tracking facts.",
                markup=False,
                classes="cleanup-blocker",
            )
        summary = target_summary(self.preview, target)
        if summary:
            yield Static(summary, markup=False, classes="cleanup-summary")
        with Collapsible(
            title="Details and recovery", id=f"cleanup-evidence-{self.index}"
        ):
            yield Static(target_evidence(target), markup=False)
        if target.kind == "worktree" and self.preview.ignored:
            with Collapsible(
                title="View ignored paths",
                id="cleanup-paths",
            ):
                yield Static(
                    "\n".join(self.preview.ignored),
                    markup=False,
                    id="cleanup-path-list",
                )

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        if isinstance(event.widget, CleanupChoice):
            # Keep the reason and consequences in view with the focused choice,
            # rather than scrolling only its checkbox above the fixed footer.
            self.scroll_visible(animate=False)

    def choice(self) -> CleanupChoice | None:
        return None if self.primary else self.query_one(CleanupChoice)


class CleanupScreen(ModalScreen[CleanupConfirmation | None]):
    """Preview a Cleanup and collect the selection a person confirms."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel", "Cancel"),
        ("f", "fetch", "Fetch & prune remotes"),
    ]
    # The three facts a Remote Fetch changes while the preview is open; each
    # change re-derives the controls, so no caller refreshes them by hand.
    busy = reactive(False, bindings=True)
    preview_valid = reactive(True)
    fetch_status = reactive("")

    @dataclass(eq=False)
    class FetchRequested(Message):
        """Request Remote Fetch for the captured Cleanup preview."""

        screen: CleanupScreen

    def __init__(
        self,
        request: CleanupRequest,
        preview: CleanupPreview,
        *,
        changed: bool = False,
        fetched_at: str | None = None,
    ) -> None:
        super().__init__()
        self.request = request
        self.preview = preview
        self.changed = changed
        self.fetched_at = fetched_at
        self.verified_remotes: frozenset[str] | None = None
        primary = primary_target(preview)
        self.primary_identity = primary.identity if primary is not None else None
        # The optional targets the next compose checks: the defaults on a
        # first preview only. A preview reopened because the state changed
        # since confirmation, like one refreshed in place, never re-arms one.
        self.chosen = () if changed else default_choices(preview)
        self._rebuilding = False

    @property
    def primary(self) -> CleanupTarget | None:
        return (
            self.preview.target(self.primary_identity)
            if self.primary_identity
            else None
        )

    @property
    def can_confirm(self) -> bool:
        if self.preview.refusals:
            return False
        if self.primary_identity is not None:
            return self.primary is not None and self.primary.available
        return self.preview.kind == "branch" and bool(self.preview.selectable)

    @property
    def verb(self) -> str:
        """The dialog's title and its confirm button's fixed label."""
        return "Remove Worktree" if self.preview.kind == "worktree" else "Delete Branch"

    @override
    def compose(self) -> ComposeResult:
        preview = self.preview
        verb = self.verb
        subject = (
            Path(preview.subject).name
            if preview.kind == "worktree"
            else preview.subject
        )
        with Vertical(id="cleanup-dialog"):
            with VerticalScroll(id="cleanup-body"):
                yield Static(verb, id="cleanup-title")
                yield Static(subject, markup=False, id="cleanup-subject")
                yield Static(
                    f"Anchor: {preview.anchor}", markup=False, id="cleanup-context"
                )
                if self.changed:
                    yield Static(
                        CHANGED_HELP, id="cleanup-help", classes="cleanup-blocker"
                    )
                for refusal in preview.refusals:
                    yield Static(
                        f"Blocked: {refusal}", markup=False, classes="cleanup-blocker"
                    )
                if preview.kind == "worktree" or any(
                    target.kind == "remote-branch"
                    or (
                        target.integration
                        and (target.integration.integration_ref or "").startswith(
                            "refs/remotes/"
                        )
                    )
                    for target in preview.targets
                ):
                    fetched_at = self.fetched_at or next(
                        (
                            target.observed_at
                            for target in preview.targets
                            if target.observed_at
                        ),
                        None,
                    )
                    freshness = "Uses last fetched state. Press f here to fetch and prune remotes."
                    if fetched_at:
                        freshness += "\nRepository fetch timestamp: " + fetched_at
                        freshness += (
                            " ("
                            + fetch_age_text(
                                fetched_at, datetime.now(UTC)
                            ).removeprefix("remote last fetched ")
                            + "; not per-remote verification)"
                        )
                    yield Static(freshness, id="cleanup-freshness")
                if preview.kind == "branch" and self.primary_identity is None:
                    yield Static(
                        "Select each concrete Branch to delete below; unselected targets are retained.",
                        classes="cleanup-summary",
                    )
                yield Static(self.fetch_status, markup=False, id="cleanup-fetch-status")
                with Vertical(id="cleanup-targets"):
                    for index, target in enumerate(preview.targets):
                        if index == 1 and preview.kind == "worktree":
                            yield Static("Also remove", classes="cleanup-summary")
                        yield CleanupTargetView(
                            preview,
                            target,
                            index,
                            primary=target.identity == self.primary_identity,
                            chosen=target.identity in self.chosen,
                            unverified_remote=(
                                target.kind == "remote-branch"
                                and self.verified_remotes is not None
                                and target.remote not in self.verified_remotes
                            ),
                        )
                with Vertical(id="cleanup-callout"):
                    yield Static("Confirming will:", id="cleanup-callout-title")
                    yield Static("", markup=False, id="cleanup-callout-lines")
            with Vertical(id="cleanup-footer"):
                yield Static("", id="cleanup-problem")
                with Horizontal(id="cleanup-actions"):
                    yield Button(
                        "Cancel" if self.can_confirm else "Close", id="cleanup-cancel"
                    )
                    if self.can_confirm:
                        yield Button(verb, id="cleanup-confirm")
                yield Footer()

    def on_mount(self) -> None:
        self.refresh_state()
        self.focus_choice()

    @override
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        return None if action == "fetch" and self.busy else True

    def targets(self) -> tuple[CleanupTargetView, ...]:
        return tuple(self.query(CleanupTargetView))

    def focus_choice(self) -> None:
        choice = next(
            (
                choice
                for one in self.targets()
                if (choice := one.choice()) is not None and not choice.disabled
            ),
            None,
        )
        if choice is not None:
            choice.focus()
        elif self.can_confirm:
            # Never the confirm button: a stray Enter after x must not confirm.
            self.query_one("#cleanup-body", VerticalScroll).focus()
        else:
            self.query_one("#cleanup-cancel", Button).focus()

    def selected(self) -> tuple[str, ...]:
        """Include the fixed subject and explicitly selected additional targets."""
        if not self.can_confirm:
            return ()
        return tuple(
            one.target.identity
            for one in self.targets()
            if one.target.available
            and (one.primary or ((choice := one.choice()) is not None and choice.value))
        )

    def worktree_selected(self) -> bool:
        return any(
            one.target.kind == "worktree" and one.target.identity in self.selected()
            for one in self.targets()
        )

    def selection_problem(self) -> str | None:
        """Explain why the current selection cannot be confirmed."""
        if self.busy:
            return "Fetching and rebuilding this preview; wait before confirming."
        if not self.preview_valid:
            return "The preview could not be refreshed. Press f to retry or cancel."
        selected = self.selected()
        if not self.can_confirm:
            return "Nothing here can be deleted."
        if not selected:
            return (
                "Select what to remove."
                if self.preview.kind == "worktree"
                else "Select what to delete."
            )
        for identity in selected:
            target = self.preview.target(identity)
            if target and target.requires and target.requires not in selected:
                required = self.preview.target(target.requires)
                return f"{target.label} requires removing {required.label if required else 'the Worktree'}."
        return None

    def refresh_state(self) -> None:
        if self._rebuilding or not self.query("#cleanup-problem"):
            return
        for one in self.targets():
            choice = one.choice()
            if choice is None:
                continue
            choice.disabled = (
                self.busy or not self.can_confirm or not one.target.available
            )
            if not one.target.available and choice.value:
                choice.value = False
        lines = confirmation_lines(self.preview, self.selected())
        self.query_one("#cleanup-callout", Vertical).display = bool(lines)
        self.query_one("#cleanup-callout-lines", Static).update("\n".join(lines))
        problem = self.selection_problem()
        self.query_one("#cleanup-problem", Static).update(problem or "")
        self.query_one("#cleanup-fetch-status", Static).update(self.fetch_status)
        if self.can_confirm:
            button = self.query_one("#cleanup-confirm", Button)
            button.disabled = self.busy or not self.preview_valid
            button.variant = "error" if problem is None else "default"
        self.refresh_bindings()

    def on_checkbox_changed(self, _event: Checkbox.Changed) -> None:
        self.refresh_state()

    def watch_busy(self) -> None:
        self.refresh_state()

    def watch_preview_valid(self) -> None:
        self.refresh_state()

    def watch_fetch_status(self) -> None:
        self.refresh_state()

    def action_fetch(self) -> None:
        if not self.busy:
            self.post_message(self.FetchRequested(self))

    def begin_fetch(self) -> None:
        """Hold destructive confirmation while this preview is refreshed."""
        self.busy = True
        self.fetch_status = "Fetching and pruning remotes…"

    async def replace_preview(
        self, preview: CleanupPreview | None, status: str
    ) -> None:
        """Refresh evidence without silently widening the confirmed removal scope."""
        choices = (
            retained_choices(self.preview, preview, self.selected()) if preview else ()
        )
        changed = preview is not None and preview != self.preview
        self.preview_valid = preview is not None
        self.fetch_status = status
        if preview is not None:
            # The controls the new preview needs exist only after the
            # recompose, so nothing re-derives them until it has happened.
            self._rebuilding = True
            try:
                self.preview = preview
                # A refresh never re-applies the first preview's defaults: a
                # changed or new target starts unchecked (ADR 0036, ADR 0054).
                self.chosen = choices
                if changed:
                    self.fetch_status += (
                        "\nPreview updated. Review its current facts before confirming."
                    )
                await self.recompose()
            finally:
                self._rebuilding = False
            if (
                not self.is_mounted
                or not self.is_attached
                or self not in self.app.screen_stack
            ):
                return
        # begin_fetch raised busy, so lowering it is what re-derives the
        # rebuilt controls; nothing else refreshes them after the recompose.
        self.busy = False
        self.focus_choice()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        problem = self.selection_problem()
        if problem is not None:
            self.notify(problem, title="Nothing deleted", severity="warning")
            self.focus_choice()
            return
        # The dialog discloses the ignored content instead of asking for a
        # tick, so removing the Worktree is the acknowledgement (ADR 0054).
        self.dismiss(
            CleanupConfirmation(
                self.request,
                self.preview.fingerprint,
                self.selected(),
                delete_ignored=self.worktree_selected(),
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cleanup-confirm":
            self.action_confirm()
        elif event.button.id == "cleanup-cancel":
            self.action_cancel()


class CleanupReportScreen(ModalScreen[None]):
    """Show what a Cleanup did to each target, with the recovery commands."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "close", "Close"),
        ("enter", "close", "Close"),
    ]

    def __init__(self, report: CleanupReport) -> None:
        super().__init__()
        self.report = report

    @override
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="cleanup-report-dialog"):
            yield Static("CLEANUP", id="cleanup-report-title")
            yield Static(
                "\n".join(describe_cleanup_report(self.report)), id="cleanup-report"
            )
            with Horizontal(id="cleanup-report-actions"):
                yield Button("Close", id="cleanup-report-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.action_close()
