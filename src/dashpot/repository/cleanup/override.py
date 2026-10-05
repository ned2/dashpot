"""Let a person's acknowledgement lift the ``sub-agent`` blockers a preview names.

A live sub-agent blocks the removal of every Worktree of its Repository,
because no hook says where it works (ADR 0066). A person who knows that none
of the sub-agents a preview lists works in the Worktree may say so for
exactly that set. The acknowledgement lifts those blockers and nothing else,
and only while the processes inside the Worktree were all checked and none
was found, since that check is the evidence that no sub-agent's command runs
there (ADR 0104, ADR 0112).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ...core.runtime_events import fitting_identities
from .targets import (
    CleanupBlocker,
    CleanupError,
    CleanupPreview,
    CleanupTarget,
    held_by_blocked_worktree,
)

# The command line's spelling of one session's acknowledged sub-agents.
DESPITE_SUBAGENTS_FLAG = "--despite-subagents"


@dataclass(frozen=True, slots=True)
class ListedSubagents:
    """One Agent Session's sub-agents listed as working, by agent ID."""

    session_id: str
    agents: frozenset[str]

    @property
    def argument(self) -> str:
        """``SESSION:AGENT,AGENT``: how the command line names this set."""
        return f"{self.session_id}:{','.join(sorted(self.agents))}"

    @property
    def spelled(self) -> bool:
        """Whether the command line can name this set: every ID an identifier.

        A hook record accepts any agent ID. One holding ``,`` or ``:`` would
        read back as another set, which an exact set can never match, and one
        holding a space or a shell character would not survive being pasted
        into a shell; an opaque identifier without ``:`` is neither.
        """
        identities = (self.session_id, *self.agents)
        return len(fitting_identities(identities)) == len(identities) and not any(
            ":" in identity for identity in identities
        )


Acknowledgement = frozenset[ListedSubagents]

# No sub-agent acknowledged: what a Cleanup confirms unless a person says otherwise.
NO_ACKNOWLEDGEMENT: Acknowledgement = frozenset[ListedSubagents]()


def listed_by(blockers: Iterable[CleanupBlocker]) -> Acknowledgement:
    """The sub-agents ``sub-agent`` blockers list as working, one set per session.

    Two harnesses' sessions sharing an ID are one session here, as the
    command line names a session by its ID alone.
    """
    agents: dict[str, set[str]] = {}
    for blocker in blockers:
        if blocker.kind == "sub-agent" and blocker.session_id is not None:
            agents.setdefault(blocker.session_id, set()).update(blocker.agents)
    return frozenset(
        ListedSubagents(session, frozenset(named)) for session, named in agents.items()
    )


def described(acknowledgement: Acknowledgement) -> str:
    """Every set as the command line names it, in a stable order, or ``none``."""
    arguments = sorted(listed.argument for listed in acknowledgement)
    return " ".join(arguments) if arguments else "none"


def parse_despite_subagents(values: Sequence[str]) -> Acknowledgement:
    """Read ``--despite-subagents SESSION:AGENT,AGENT`` values, one per session.

    A malformed value, or a session named twice, is a usage mistake: an
    acknowledgement must say exactly which sub-agents it covers.
    """
    sets: dict[str, frozenset[str]] = {}
    for value in values:
        session, colon, listed = value.partition(":")
        agents = listed.split(",")
        if not colon or not session or not all(agents):
            raise CleanupError(
                f"{DESPITE_SUBAGENTS_FLAG} takes SESSION:AGENT[,AGENT…], one session "
                f"each time, as the preview names them; got {value!r}"
            )
        if session in sets:
            raise CleanupError(
                f"{DESPITE_SUBAGENTS_FLAG} names session {session} more than once; "
                "name each session once, with all its agents"
            )
        sets[session] = frozenset(agents)
    return frozenset(
        ListedSubagents(session, agents) for session, agents in sets.items()
    )


def worktree_target(preview: CleanupPreview) -> CleanupTarget | None:
    """The Worktree a Worktree preview would remove, or None for a Branch preview."""
    if preview.kind != "worktree":
        return None
    return next(
        (target for target in preview.targets if target.kind == "worktree"), None
    )


def listed_in(preview: CleanupPreview) -> Acknowledgement:
    """The sub-agents a Worktree preview lists as working, whether or not offered."""
    worktree = worktree_target(preview)
    return NO_ACKNOWLEDGEMENT if worktree is None else listed_by(worktree.blockers)


def override_offer(preview: CleanupPreview) -> Acknowledgement:
    """The sub-agents a person may acknowledge to remove this Worktree, or none.

    Offered only when ``sub-agent`` blockers are all that hold the Worktree
    and the processes inside it were all checked: every other blocker
    stands, and a scan that fell short cannot show that no sub-agent's
    command runs there.
    """
    worktree = worktree_target(preview)
    if (
        worktree is None
        or preview.refusals
        or preview.unchecked_processes is not None
        or not worktree.blockers
        or any(blocker.kind != "sub-agent" for blocker in worktree.blockers)
    ):
        return NO_ACKNOWLEDGEMENT
    return listed_by(worktree.blockers)


def lifted(preview: CleanupPreview, acknowledged: Acknowledgement) -> frozenset[str]:
    """The targets an acknowledgement makes available: none unless it is exact.

    The Worktree, when its acknowledged sub-agents are exactly those listed,
    and each Branch blocked only because it is checked out there: a Branch
    also in use in another Worktree, as one being rebased there, stays
    blocked.
    """
    worktree = worktree_target(preview)
    if worktree is None or not acknowledged or acknowledged != override_offer(preview):
        return frozenset[str]()
    return frozenset(
        {worktree.identity}
        | {
            target.identity
            for target in preview.targets
            if target.requires == worktree.identity
            and worktree.path is not None
            and target.blockers
            == (
                held_by_blocked_worktree(
                    worktree.path, remote=target.kind == "remote-branch"
                ),
            )
        }
    )


def override_refusal(
    preview: CleanupPreview,
    acknowledged: Acknowledgement,
    confirmed: Acknowledgement | None = None,
) -> tuple[str, bool] | None:
    """Why an acknowledgement cannot lift this preview's ``sub-agent`` blockers, if so.

    The sub-agents listed now must be exactly the ones acknowledged, and the
    processes inside the Worktree must all have been checked. A Worktree
    that some other blocker holds is refused by that blocker instead.
    Beside the reason comes whether the preview changed: whether the set
    listed now differs from the one the ``confirmed`` preview listed, which
    is the acknowledged set when the caller does not say.
    A set typed against an unchanged preview is a mistake, not a change,
    whether or not the preview offered the override.
    """
    if not acknowledged:
        return None
    if worktree_target(preview) is None:
        return (
            f"{DESPITE_SUBAGENTS_FLAG} acknowledges sub-agents only for removing "
            "a Worktree",
            False,
        )
    listed = listed_in(preview)
    if listed != acknowledged:
        changed = listed != (acknowledged if confirmed is None else confirmed)
        return (
            f"the sub-agents listed as working are {described(listed)}, not the "
            f"{described(acknowledged)} acknowledged; nothing was removed: check "
            "them again against this preview",
            changed,
        )
    if preview.unchecked_processes is not None:
        return (
            "sub-agents cannot be acknowledged while the processes inside the "
            f"Worktree were not all checked: {preview.unchecked_processes}",
            False,
        )
    return None
