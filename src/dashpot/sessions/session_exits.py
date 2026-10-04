"""Name each harness's way out of a Worktree for its Agent Sessions.

Every session-derived Cleanup blocker and ``dashpot work show`` read it, so a
person is told one way to move or end a session, whichever surface asks,
including when a sub-agent the session lists may only have been interrupted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..core.model import HARNESS_DISPLAY, Harness


@dataclass(frozen=True, slots=True)
class SessionExit:
    """How a person frees a Worktree from one harness's Agent Session.

    ``move`` takes the session, conversation and all, out of the Worktree;
    ``end`` ends it. Each is a clause that names the session as "that
    session"; ``{session_id}`` in either is replaced by its identity, or by
    ``<session id>`` where no one session is meant.
    """

    move: str
    end: str


# Each harness's way out, which every session-derived Cleanup blocker and
# ``work show`` read: a harness adds its entry here, and one without an entry
# is given ``ANY_SESSION_EXIT``.
SESSION_EXITS: Mapping[Harness, SessionExit] = {
    # ExitWorktree(keep) returns only a session EnterWorktree brought here; a
    # shell cd back into the checkout the session started in places it there
    # without its run (ADR 0074); a session started here can only be ended.
    "claude-code": SessionExit(
        move="run ExitWorktree with action: keep in that session if "
        "EnterWorktree brought it here, or cd its shell back to the checkout "
        "it started in if it came by cd (leaving any Agent Run here)",
        end="end that session",
    ),
    # The declared resume of ADR 0029 carries an Agent Run; a session without
    # one just resumes elsewhere. A daemon-hosted thread outlives its
    # terminal until the daemon unloads it (ADR 0072).
    "codex": SessionExit(
        move="resume that session elsewhere with codex resume {session_id} "
        "-C <worktree> once its client exits, running dashpot work relocate "
        "<worktree> in it first if it holds an Agent Run",
        end="end that session's client (a daemon-hosted thread ends about "
        "60 s after its last client leaves)",
    ),
    # Quitting an OpenCode client ends and moves nothing: the session lives in
    # its server. It leaves by a move, ends by its deletion, which its server
    # publishes, or reads gone once its server stops (ADR 0090).
    "opencode": SessionExit(
        move="move that session to another location in OpenCode",
        end="delete that session with opencode session delete {session_id}, "
        "or stop the OpenCode server it runs in, with opencode service stop or "
        "by quitting its --standalone client, which leaves every Agent Run on "
        "that server orphaned",
    ),
}


ANY_SESSION_EXIT = SessionExit(
    move="move that session out of this Worktree with its harness's own tool",
    end="end that session",
)


def session_exit(harness: Harness) -> SessionExit:
    """The way out of a Worktree for a session of ``harness``."""
    return SESSION_EXITS.get(harness, ANY_SESSION_EXIT)


def listed_subagents(count: int) -> str:
    """``1 sub-agent listed as working``: how many sub-agents a session lists."""
    noun = "sub-agent" if count == 1 else "sub-agents"
    return f"{count} {noun} listed as working"


def unreported_subagent_stop(harness: Harness) -> str:
    """Why a sub-agent listed as working may not be, and the way out if none is.

    A session keeps a sub-agent in its live set until the harness's
    ``SubagentStop``, or until the session ends, starts again or its Host
    Process is gone. A Codex child interrupted through its own thread
    publishes no ``SubagentStop`` (#374), so the sentence names the
    harness's way to end the session rather than guessing which sub-agent is
    still working.
    """
    return (
        f"Dashpot lists a sub-agent until {HARNESS_DISPLAY[harness]} reports "
        f"that it stopped, which an interrupted one may never do, so if none "
        f"is still working, "
        f"{session_exit(harness).end.replace('{session_id}', '<session id>')}"
    )


def forget_subagents_command(session_id: str) -> str:
    """The command that forgets the sub-agents an ended session still lists."""
    return f"dashpot work forget-subagents {session_id}"


def ended_session_subagent_stop(harness: Harness, session_id: str) -> str:
    """Why a sub-agent an ended session lists may not be working, and the way out.

    An ended record keeps the sub-agents its session left working until each
    ``SubagentStop`` or until the Host Process is gone (ADR 0095). A Codex
    worker whose lead is deleted ends with it and reports nothing, as does a
    child interrupted through its own thread (#374), so the sentence names
    the command that forgets them once a person has checked.
    """
    return (
        f"Dashpot lists a sub-agent of an ended session until "
        f"{HARNESS_DISPLAY[harness]} reports that it stopped or the "
        f"session's process exits, which one that ended with its session or "
        f"was interrupted may never do, so if none is still working, run "
        f"{forget_subagents_command(session_id)}"
    )
