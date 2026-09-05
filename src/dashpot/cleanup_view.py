"""The dashboard's Cleanup modals: preview and select, then the outcomes.

The ``x`` key on a Branches or Worktrees row opens :class:`CleanupScreen`
over the preview ``cleanup.inspect_cleanup`` produced off the event loop.
Every target starts unselected and an unavailable one cannot be selected;
the destructive button stays disabled until the selection is one
``perform_cleanup`` would accept — every required target selected and the
Worktree's ignored content acknowledged — and Escape always cancels. The
screen dismisses with the :class:`CleanupConfirmation` the app performs, or
None. A successful Cleanup returns directly to the dashboard with one toast
line per outcome; :class:`CleanupReportScreen` preserves the full detail for
a refused or unknown outcome.
"""

from __future__ import annotations

from typing import ClassVar, cast

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, SelectionList, Static
from textual.widgets.selection_list import Selection
from typing_extensions import override

from .cleanup import (
    CHANGED_SINCE_PREVIEW,
    INTEGRATION_WORDS,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    CleanupTarget,
    describe_cleanup_report,
)
from .marked_widgets import MarkedCheckbox, MarkedSelectionList

SELECT_HELP = (
    "Select the targets to delete. Nothing is deleted until Delete selected is "
    "pressed; Escape cancels."
)
CHANGED_HELP = (
    f"{CHANGED_SINCE_PREVIEW[0].upper()}{CHANGED_SINCE_PREVIEW[1:]}. This is the "
    "revised preview; select and confirm again."
)


def target_line(target: CleanupTarget) -> str:
    """The one line a target shows in the list: what, where, and whether it can go."""
    state = " — unavailable" if not target.available else ""
    where = target.path if target.kind == "worktree" else target.ref
    return f"{target.label}{state}  {where} @ {target.expected[:7]}"


def target_details(preview: CleanupPreview) -> str:
    """Every target's gate and consequences, under its label, for the text below the list."""
    blocks: list[str] = []
    for target in preview.targets:
        lines = [target.label]
        if target.integration is not None:
            lines.append(f"  {INTEGRATION_WORDS[target.integration.state]}")
        if target.requires is not None:
            required = preview.target(target.requires)
            name = required.label if required is not None else target.requires
            lines.append(f"  only together with {name}")
        lines.extend(f"  blocked: {blocker.detail}" for blocker in target.blockers)
        lines.extend(f"  → {consequence}" for consequence in target.consequences)
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def ignored_prompt(preview: CleanupPreview) -> str:
    """The acknowledgement a Worktree's ignored content asks for."""
    shown = ", ".join(preview.ignored[:3])
    more = f", … ({len(preview.ignored)} in all)" if len(preview.ignored) > 3 else ""
    return (
        f"Delete the {len(preview.ignored)} ignored path(s) inside it too: "
        f"{shown}{more}"
    )


class CleanupScreen(ModalScreen[CleanupConfirmation | None]):
    """Preview a Cleanup and collect the selection a person confirms."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        request: CleanupRequest,
        preview: CleanupPreview,
        *,
        changed: bool = False,
    ) -> None:
        super().__init__()
        self.request = request
        self.preview = preview
        self.changed = changed

    @override
    def compose(self) -> ComposeResult:
        preview = self.preview
        verb = "DELETE BRANCH" if preview.kind == "branch" else "REMOVE WORKTREE"
        # The preview scrolls when it outgrows the terminal; the acknowledgement,
        # the reason the selection cannot be confirmed yet, and the buttons are
        # docked below it so they are always in view and never scrolled under.
        with VerticalScroll(id="cleanup-dialog", can_focus=False):
            with Vertical(id="cleanup-footer"):
                if preview.ignored:
                    yield MarkedCheckbox(
                        ignored_prompt(preview), value=False, id="cleanup-ignored"
                    )
                yield Static("", id="cleanup-problem")
                with Horizontal(id="cleanup-actions"):
                    yield Button("Cancel", id="cleanup-cancel")
                    yield Button("Delete selected", id="cleanup-confirm")
            yield Static(f"{verb}  {preview.subject}", id="cleanup-title")
            yield Static(
                CHANGED_HELP if self.changed else SELECT_HELP, id="cleanup-help"
            )
            for refusal in preview.refusals:
                yield Static(f"Refused: {refusal}", classes="cleanup-refusal")
            yield MarkedSelectionList[str](
                *(
                    Selection(
                        target_line(target),
                        target.identity,
                        id=target.identity,
                        disabled=not target.available,
                    )
                    for target in preview.targets
                ),
                id="cleanup-targets",
            )
            yield Static(target_details(preview), id="cleanup-details")

    def on_mount(self) -> None:
        targets = self.targets()
        targets.focus()
        self.refresh_state()

    def targets(self) -> SelectionList[str]:
        return cast(
            "SelectionList[str]", self.query_one("#cleanup-targets", SelectionList)
        )

    def selected(self) -> tuple[str, ...]:
        """The selected identities in the preview's order."""
        chosen = set(self.targets().selected)
        return tuple(
            target.identity
            for target in self.preview.targets
            if target.identity in chosen
        )

    def ignored_acknowledged(self) -> bool:
        if not self.preview.ignored:
            return False
        return self.query_one("#cleanup-ignored", Checkbox).value

    def acknowledgement_missing(self) -> bool:
        """Whether a selected Worktree's ignored content still awaits its checkbox."""
        if not self.preview.ignored or self.ignored_acknowledged():
            return False
        return any(
            target.kind == "worktree"
            for identity in self.selected()
            if (target := self.preview.target(identity)) is not None
        )

    def selection_problem(self) -> str | None:
        """Why the selection cannot be confirmed yet, or None when it can."""
        selected = self.selected()
        if not self.preview.selectable:
            return "Nothing here can be deleted."
        if not selected:
            return "Select at least one target."
        for identity in selected:
            target = self.preview.target(identity)
            if target is None or target.requires is None:
                continue
            if target.requires not in selected:
                required = self.preview.target(target.requires)
                name = required.label if required is not None else target.requires
                return f"{target.label} can only be deleted together with {name}."
        if self.acknowledgement_missing():
            return (
                f"Acknowledge that the {len(self.preview.ignored)} ignored "
                f"path(s) are deleted with the Worktree."
            )
        return None

    def refresh_state(self) -> None:
        # An unavailable target never stays selected, whatever toggled it.
        targets = self.targets()
        for identity in list(targets.selected):
            target = self.preview.target(identity)
            if target is None or not target.available:
                targets.deselect(identity)
        problem = self.selection_problem()
        self.query_one("#cleanup-problem", Static).update(problem or "")
        # The button always answers a press; it turns red once a press would
        # delete. A disabled button would still light up under the mouse and
        # swallow the click without a word.
        self.query_one("#cleanup-confirm", Button).variant = (
            "error" if problem is None else "default"
        )

    def on_selection_list_selected_changed(
        self, _event: SelectionList.SelectedChanged[str]
    ) -> None:
        self.refresh_state()

    def on_checkbox_changed(self, _event: Checkbox.Changed) -> None:
        self.refresh_state()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        problem = self.selection_problem()
        if problem is not None:
            # A premature press deletes nothing and points at what is missing.
            self.notify(problem, title="Nothing deleted", severity="warning")
            if self.acknowledgement_missing():
                self.query_one("#cleanup-ignored", Checkbox).focus()
            else:
                self.targets().focus()
            return
        self.dismiss(
            CleanupConfirmation(
                self.request,
                self.preview.fingerprint,
                self.selected(),
                delete_ignored=self.ignored_acknowledged(),
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
