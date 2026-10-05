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
from textual.content import Content
from textual.events import DescendantFocus
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Footer, Static

from ..core.ages import relative_age
from ..core.model import HARNESS_DISPLAY
from ..core.text import counted
from ..repository.cleanup import (
    CHANGED_SINCE_PREVIEW,
    NO_ACKNOWLEDGEMENT,
    Acknowledgement,
    CleanupBlocker,
    CleanupConfirmation,
    CleanupPreview,
    CleanupReport,
    CleanupRequest,
    CleanupTarget,
    default_choices,
    describe_cleanup_report,
    lifted,
    listed_by,
    listed_in,
    override_offer,
    primary_target,
    retained_choices,
    sub_agent_scope,
    unchecked_processes_note,
    worktree_target,
)
from ..repository.refs import REMOTE_REF_PREFIX, short_ref
from .branch_cells import fetch_age_text
from .marked_widgets import MarkedCheckbox

CHANGED_HELP = (
    f"{CHANGED_SINCE_PREVIEW[0].upper()}{CHANGED_SINCE_PREVIEW[1:]}. "
    "Nothing was deleted. Select and confirm again."
)


def integration_ref_label(ref: str | None) -> str:
    """Label the ref integration was judged against, or name the Integration Branch."""
    return short_ref(ref) if ref else "the Integration Branch"


def judged_against_remote_tracking(target: CleanupTarget) -> bool:
    """Whether integration was judged against a Remote-Tracking Branch.

    Such a judgement is only as fresh as the last Remote Fetch: Dashpot never
    fetches on its own, so a merged Pull Request whose commit has not been
    fetched still reads as unintegrated.
    """
    fact = target.integration
    return fact is not None and (fact.integration_ref or "").startswith(
        REMOTE_REF_PREFIX
    )


def target_ref_label(target: CleanupTarget) -> str:
    """Label a Branch target's ref as a person reads it."""
    return short_ref(target.ref or "")


def remote_branch_name(target: CleanupTarget) -> str:
    """The Branch's name at its remote, without the remote's own prefix."""
    return target_ref_label(target).removeprefix(f"{target.remote}/")


def required_label(preview: CleanupPreview, target: CleanupTarget) -> str:
    """Name the target ``target`` can only be selected with, or the Worktree."""
    required = preview.target(target.requires) if target.requires else None
    return required.label if required else "the Worktree"


FETCH_HINT = "If it has since merged, press f to fetch and check again."

NOTHING_DELETABLE = "Nothing here can be deleted."

# How many ignored path names the confirmation callout spells out.
CALLOUT_IGNORED_NAMES = 3


def rests_on_remote_facts(preview: CleanupPreview) -> bool:
    """Whether the preview rests on facts only a Remote Fetch refreshes."""
    return preview.kind == "worktree" or any(
        target.kind == "remote-branch" or judged_against_remote_tracking(target)
        for target in preview.targets
    )


def freshness_line(
    preview: CleanupPreview, fetched_at: str | None, now: datetime
) -> Static | None:
    """Say when the remotes were last fetched, where the preview rests on them.

    ``fetched_at`` is the Repository's last fetch as the preview knows it,
    else the first target observed with one; the hover says it is the
    Repository's, not a verification of each remote.
    """
    if not rests_on_remote_facts(preview):
        return None
    fetched_at = fetched_at or next(
        (target.observed_at for target in preview.targets if target.observed_at),
        None,
    )
    age = fetch_age_text(fetched_at, now)
    line = Static(age[:1].upper() + age[1:], markup=False, id="cleanup-freshness")
    if fetched_at:
        line.tooltip = Content(
            f"Repository fetch timestamp: {fetched_at} (not per-remote verification)"
        )
    return line


def blocker_summary(blocker: CleanupBlocker, target: CleanupTarget) -> str:
    """Keep each blocking condition visible beside its target.

    An integration block judged against a Remote-Tracking Branch may only be
    stale, so it says how to check again.
    """
    summary = _blocker_text(blocker, target)
    integration = blocker.kind in {"unintegrated", "unknown-integration"}
    if integration and judged_against_remote_tracking(target):
        return f"{summary} {FETCH_HINT}"
    return summary


def _blocker_text(blocker: CleanupBlocker, target: CleanupTarget) -> str:
    # A checked-out blocker is shown whole, as its detail: the Branch may be
    # checked out, rebased, or bisected, here or in another Worktree, and
    # the detail names which and where.
    if blocker.kind == "unintegrated" and target.integration:
        fact = target.integration
        return (
            f"{counted(fact.unintegrated_commits or 0, 'commit')} not reachable from "
            f"{integration_ref_label(fact.integration_ref)}."
        )
    # An agent-session blocker is shown whole, as its detail: it names the
    # session, whether it is live here, and its harness's way out.
    summaries = {
        "dirty": "Uncommitted changes or untracked files; inspect before removal.",
        "locked": "The Worktree is locked; inspect the lock before removal.",
        # Claude Code and Codex publish sub-agent boundaries (ADR 0066, ADR 0067).
        "sub-agent": "A sub-agent may be working here: Dashpot cannot tell "
        "where one works. Wait for it to finish, or end its session.",
        # The detail names each process and where it runs (ADR 0104).
        "process": "A process is running inside this Worktree; end it or move "
        "it out before removal.",
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
            lines.append("Keeps each Branch below that is not selected.")
        if preview.ignored:
            lines.append(f"Includes {ignored_description(preview)}.")
    else:
        fact = target.integration
        if fact and fact.state == "integrated":
            lines.append(
                f"Commits integrated into {integration_ref_label(fact.integration_ref)}."
            )
        elif fact and fact.state == "content-integrated":
            original = fact.unintegrated_commits or 0
            lines.append(
                f"Content integrated into {integration_ref_label(fact.integration_ref)}; "
                f"{counted(original, 'original commit')} "
                f"{'is' if original == 1 else 'are'} not retained there."
            )
        if target.requires:
            lines.append(f"Requires removing {required_label(preview, target)}.")
        if target.kind == "remote-branch":
            lines.append(
                f"Deletes the Branch on {target.remote}; refuses if its tip changed."
            )
    return "\n".join(lines)


# A labelled line of a target's details, or None for the gap before its blockers.
TargetFact = tuple[str, str] | None


def target_facts(target: CleanupTarget, now: datetime) -> list[TargetFact]:
    """Identify a target and each blocker in full, one labelled fact a line.

    What the summary already says is left out, and so are recovery commands:
    the preview is for deciding, and ``dashpot branch delete`` or ``worktree
    remove`` still prints them for a record.
    """
    commit = target.expected[:7]
    facts: list[TargetFact] = []
    if target.kind == "worktree":
        facts += [("Path", target.path or ""), ("HEAD", commit)]
    elif target.kind == "local-branch":
        facts += [("Branch", target_ref_label(target)), ("Commit", commit)]
    else:
        age = relative_age(target.observed_at, now)
        facts += [
            ("Branch", f"{remote_branch_name(target)} at {target.remote}"),
            (
                "Commit",
                f"{commit}, as of the last Repository fetch ({age})" if age else commit,
            ),
            ("Lease", f"Refuses unless {target.remote} still has {commit}."),
        ]
    if target.blockers:
        facts.append(None)
    for blocker in target.blockers:
        # Verbatim: a detail may open with a Branch name, and case is its identity.
        facts.append(("Blocked", blocker.detail))
        if blocker.command:
            facts.append(("Next", blocker.command))
    return facts


class TargetDetails(Vertical):
    """A target's facts, each value wrapping in a column beside its label."""

    def __init__(self, facts: Sequence[TargetFact]) -> None:
        super().__init__(classes="cleanup-facts")
        self.facts = tuple(facts)

    @override
    def compose(self) -> ComposeResult:
        for fact in self.facts:
            if fact is None:
                yield Static("", classes="cleanup-fact-gap")
                continue
            label, value = fact
            with Horizontal(classes="cleanup-fact"):
                yield Static(label, classes="cleanup-fact-label")
                yield Static(value, markup=False, classes="cleanup-fact-value")


def despite_sessions(preview: CleanupPreview) -> list[str]:
    """Name each session whose listed sub-agents an acknowledgement covers, with its count.

    One line per session, as the acknowledgement and its callout count them;
    a harness is named when the session's blockers agree on one.
    """
    worktree = worktree_target(preview)
    if worktree is None or not override_offer(preview):
        return []
    harnesses: dict[str, set[str]] = {}
    for blocker in worktree.blockers:
        if blocker.session_id is not None and blocker.harness is not None:
            harnesses.setdefault(blocker.session_id, set()).add(
                HARNESS_DISPLAY[blocker.harness]
            )
    lines: list[str] = []
    for listed in sorted(listed_by(worktree.blockers), key=lambda one: one.session_id):
        named = harnesses.get(listed.session_id, set())
        harness = next(iter(named)) if len(named) == 1 else "Agent"
        agents = sorted(listed.agents)
        lines.append(
            f"{harness} session {listed.session_id}: "
            f"{counted(len(agents), 'sub-agent')} ({', '.join(agents)})"
        )
    return lines


def confirmation_lines(
    preview: CleanupPreview,
    selected: Sequence[str],
    acknowledged: Acknowledgement = NO_ACKNOWLEDGEMENT,
) -> list[str]:
    """State what confirming the selection removes and deletes, one target a line.

    The confirm button's label never changes, so this recap is where the
    selection is read before confirming: every selected target, the ignored
    content a Worktree takes with it, and the sub-agents it goes despite.
    """
    lines: list[str] = []
    for target in preview.targets:
        if target.identity not in selected:
            continue
        if target.kind == "worktree":
            lines.append(f"remove Worktree {target.path}")
            if acknowledged:
                agents = sum(len(listed.agents) for listed in acknowledged)
                lines.append(
                    f"  despite {counted(agents, 'sub-agent')} listed as working "
                    f"in {counted(len(acknowledged), 'session')}"
                )
            if preview.ignored:
                names = ", ".join(preview.ignored[:CALLOUT_IGNORED_NAMES])
                more = ", …" if len(preview.ignored) > CALLOUT_IGNORED_NAMES else ""
                lines.append(f"  with {ignored_description(preview)}: {names}{more}")
        elif target.kind == "local-branch":
            lines.append(f"delete local Branch {target_ref_label(target)}")
        else:
            lines.append(
                f"delete Branch {remote_branch_name(target)} at {target.remote}"
            )
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


class CleanupTargetView(Horizontal):
    """Group one Cleanup choice with its availability and consequences.

    The availability marker has a gutter of its own, so the choice, its
    reasons, and its consequences wrap beside it and never beneath it.
    """

    def __init__(
        self,
        preview: CleanupPreview,
        target: CleanupTarget,
        index: int,
        *,
        primary: bool = False,
        chosen: bool = False,
        unverified_remote: bool = False,
        grouped: bool = False,
    ) -> None:
        # The first target under "Also remove" sits directly beneath it.
        super().__init__(classes="cleanup-target" + (" -grouped" if grouped else ""))
        self.preview = preview
        self.target = target
        self.index = index
        self.primary = primary
        self.chosen = chosen
        self.unverified_remote = unverified_remote

    @override
    def compose(self) -> ComposeResult:
        with Vertical(classes="cleanup-target-body"):
            yield from self.compose_body()
        yield Static(
            "AVAILABLE" if self.target.available else "BLOCKED",
            classes="cleanup-availability"
            + (" -blocked" if not self.target.available else ""),
        )

    def compose_body(self) -> ComposeResult:
        target = self.target
        if self.primary:
            yield Static(target.label, markup=False, classes="cleanup-primary")
        else:
            yield CleanupChoice(
                target.label,
                self.chosen and target.available,
                id=f"cleanup-target-{self.index}",
                disabled=not target.available,
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
        with Collapsible(title="Details", id=f"cleanup-evidence-{self.index}"):
            yield TargetDetails(target_facts(target, datetime.now(UTC)))
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
        previous: CleanupScreen | None = None,
    ) -> None:
        """Show a preview, keeping the subject of the ``previous`` one it revises."""
        super().__init__()
        self.request = request
        self.preview = preview
        self.changed = changed
        self.fetched_at = fetched_at
        self.verified_remotes: frozenset[str] | None = None
        if previous is not None:
            # The subject stays the one the person opened (ADR 0036).
            self.primary_identity = previous.primary_identity
        else:
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
    def acknowledged(self) -> Acknowledgement:
        """The sub-agents a person has acknowledged, when the toggle is on."""
        toggles = self.query("#cleanup-despite-subagents")
        if not toggles or not toggles.first(MarkedCheckbox).value:
            return NO_ACKNOWLEDGEMENT
        return override_offer(self.preview)

    def usable(self, target: CleanupTarget) -> bool:
        """Whether ``target`` can be confirmed now, the acknowledgement included."""
        return target.available or target.identity in lifted(
            self.preview, self.acknowledged
        )

    @property
    def can_confirm(self) -> bool:
        if self.preview.refusals:
            return False
        if self.primary_identity is not None:
            primary = self.primary
            return primary is not None and (
                primary.available
                or primary.identity
                in lifted(self.preview, override_offer(self.preview))
            )
        return self.preview.kind == "branch" and bool(self.preview.selectable)

    def unverified_remote(self, target: CleanupTarget) -> bool:
        """Whether the latest fetch here left a Remote Branch's remote unverified."""
        return (
            target.kind == "remote-branch"
            and self.verified_remotes is not None
            and target.remote not in self.verified_remotes
        )

    @property
    def confirm_label(self) -> str:
        """The dialog's title and its confirm button's fixed label."""
        return "Remove Worktree" if self.preview.kind == "worktree" else "Delete Branch"

    @override
    def compose(self) -> ComposeResult:
        preview = self.preview
        label = self.confirm_label
        subject = (
            Path(preview.subject).name
            if preview.kind == "worktree"
            else preview.subject
        )
        with Vertical(id="cleanup-dialog"):
            with VerticalScroll(id="cleanup-body"):
                yield Static(label, id="cleanup-title")
                subject_view = Static(subject, markup=False, id="cleanup-subject")
                # The name is enough to recognize the subject; the full path
                # stays one hover away rather than a line of its own.
                # Plain content: a path is never parsed as markup.
                subject_view.tooltip = Content(
                    preview.subject if preview.kind == "worktree" else preview.anchor
                )
                yield subject_view
                if self.changed:
                    yield Static(
                        CHANGED_HELP, id="cleanup-help", classes="cleanup-blocker"
                    )
                for refusal in preview.refusals:
                    yield Static(
                        f"Blocked: {refusal}", markup=False, classes="cleanup-blocker"
                    )
                freshness = freshness_line(preview, self.fetched_at, datetime.now(UTC))
                if freshness is not None:
                    yield freshness
                scope = sub_agent_scope(preview)
                if scope is not None:
                    yield Static(scope, markup=False, id="cleanup-scope")
                unchecked = unchecked_processes_note(preview)
                if unchecked is not None:
                    yield Static(
                        unchecked, markup=False, id="cleanup-unchecked-processes"
                    )
                if preview.kind == "branch" and self.primary_identity is None:
                    yield Static(
                        "Select each concrete Branch to delete below; unselected targets are retained.",
                        classes="cleanup-summary",
                    )
                yield Static(self.fetch_status, markup=False, id="cleanup-fetch-status")
                if not self.can_confirm:
                    yield Static(
                        NOTHING_DELETABLE,
                        id="cleanup-unavailable",
                        classes="cleanup-blocker",
                    )
                with Vertical(id="cleanup-targets"):
                    for index, target in enumerate(preview.targets):
                        grouped = index == 1 and preview.kind == "worktree"
                        if grouped:
                            yield Static("Also remove", id="cleanup-also")
                        yield CleanupTargetView(
                            preview,
                            target,
                            index,
                            primary=target.identity == self.primary_identity,
                            chosen=target.identity in self.chosen,
                            unverified_remote=self.unverified_remote(target),
                            grouped=grouped,
                        )
                if sessions := despite_sessions(preview):
                    with Vertical(id="cleanup-despite"):
                        yield Static(
                            "Sub-agents listed as working, which Dashpot cannot "
                            "place:\n" + "\n".join(f"  {line}" for line in sessions),
                            markup=False,
                            id="cleanup-despite-sessions",
                        )
                        yield MarkedCheckbox(
                            "I have checked that none of these sub-agents works "
                            "in this Worktree",
                            False,
                            id="cleanup-despite-subagents",
                        )
                with Vertical(id="cleanup-callout"):
                    yield Static("Confirming will:", id="cleanup-callout-title")
                    yield Static("", markup=False, id="cleanup-callout-lines")
            with Vertical(id="cleanup-footer"):
                yield Static("", markup=False, id="cleanup-problem")
                with Horizontal(id="cleanup-actions"):
                    yield Button(
                        "Cancel" if self.can_confirm else "Close", id="cleanup-cancel"
                    )
                    if self.can_confirm:
                        yield Button(label, id="cleanup-confirm")
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
            if self.usable(one.target)
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
            # Said once, above the targets, rather than beside the buttons.
            return None
        primary = self.primary
        if primary is not None and not self.usable(primary):
            return (
                "Wait for the listed sub-agents to finish, or confirm that none "
                "of them works in this Worktree."
            )
        if not selected:
            return (
                "Select what to remove."
                if self.preview.kind == "worktree"
                else "Select what to delete."
            )
        for identity in selected:
            target = self.preview.target(identity)
            if target and target.requires and target.requires not in selected:
                return (
                    f"{target.label} requires removing "
                    f"{required_label(self.preview, target)}."
                )
        return None

    def refresh_state(self) -> None:
        if self._rebuilding or not self.query("#cleanup-problem"):
            return
        for one in self.targets():
            choice = one.choice()
            if choice is None:
                continue
            usable = self.usable(one.target)
            choice.disabled = self.busy or not self.can_confirm or not usable
            if not usable and choice.value:
                choice.value = False
        for toggle in self.query("#cleanup-despite-subagents").results(MarkedCheckbox):
            toggle.disabled = self.busy
        lines = confirmation_lines(
            self.preview,
            self.selected(),
            self.acknowledged if self.worktree_selected() else NO_ACKNOWLEDGEMENT,
        )
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

    def refreshing(self, fetched: str) -> None:
        """Say how the fetch went while the evidence it changed is rebuilt."""
        self.fetch_status = f"{fetched}\nRefreshing Git facts and Cleanup evidence…"

    async def finish_fetch(
        self,
        preview: CleanupPreview | None,
        status: str,
        *,
        verified_remotes: frozenset[str],
        fetched_at: str | None,
    ) -> None:
        """Take a fetch's outcome: the remotes it verified, then the rebuilt preview.

        ``preview`` is None when the evidence could not be rebuilt, which
        leaves this preview invalid with ``status`` saying why.
        """
        self.verified_remotes = verified_remotes
        self.fetched_at = fetched_at
        await self.replace_preview(preview, status)

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
            # A target's label names a remote, which is text, never markup.
            self.notify(
                problem, title="Nothing deleted", severity="warning", markup=False
            )
            self.focus_choice()
            return
        # The dialog discloses the ignored content instead of asking for a
        # tick, so removing the Worktree is the acknowledgement (ADR 0054).
        # Sub-agents are different: only the person's explicit tick vouches
        # for them, and only for the set the preview names (ADR 0112).
        removing = self.worktree_selected()
        acknowledged = self.acknowledged if removing else NO_ACKNOWLEDGEMENT
        self.dismiss(
            CleanupConfirmation(
                self.request,
                self.preview.fingerprint,
                self.selected(),
                delete_ignored=removing,
                despite_subagents=acknowledged,
                listed=listed_in(self.preview) if acknowledged else None,
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
            # Paths and Git's own words, such as ``! [remote rejected]``,
            # are shown as they are, never parsed as markup.
            yield Static(
                "\n".join(describe_cleanup_report(self.report)),
                markup=False,
                id="cleanup-report",
            )
            with Horizontal(id="cleanup-report-actions"):
                yield Button("Close", id="cleanup-report-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.action_close()
