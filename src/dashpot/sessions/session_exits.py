"""Name each harness's way out of a Worktree for its Agent Sessions.

Every session-derived Cleanup blocker and ``dashpot work show`` read it, so a
person is told one way to move or end a session, whichever surface asks,
including when a sub-agent the session lists may only have been interrupted.
Each harness's resume command lives here too, which the Sessions pane copies
for an Orphaned Agent Run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..core.model import HARNESS_DISPLAY, Harness
from ..core.shell import in_directory, shell_command
from ..core.text import counted

# The words of a resume template that stand for the session's identity and
# the directory it resumes at.
RESUME_SESSION_ID = "{session_id}"
RESUME_DIRECTORY = "{directory}"


@dataclass(frozen=True, slots=True)
class ResumeTemplate:
    """The command that resumes one harness's session at a directory.

    Each of ``argv``'s words is one argument; ``RESUME_SESSION_ID`` and
    ``RESUME_DIRECTORY`` stand for the session's identity and the directory,
    each quoted as one argument however it is spelled. With ``from_directory``
    the command runs from inside the directory, for a harness that files a
    conversation under the directory it was started in.
    """

    argv: tuple[str, ...]
    from_directory: bool = False

    def render(self, session_id: str, directory: str) -> str:
        """The command line resuming ``session_id`` at ``directory``."""
        values = {RESUME_SESSION_ID: session_id, RESUME_DIRECTORY: directory}
        argv = [values.get(word, word) for word in self.argv]
        if self.from_directory:
            return in_directory(directory, *argv)
        return shell_command(*argv)


@dataclass(frozen=True, slots=True)
class SessionExit:
    """How a person frees a Worktree from one harness's Agent Session.

    ``move`` takes the session, conversation and all, out of the Worktree;
    ``end`` ends it. Each is a clause that names the session as "that
    session"; ``{session_id}`` in either is replaced by its identity, or by
    ``<session id>`` where no one session is meant. ``resume``, where the
    harness has one, is the command that resumes a session whose process is
    gone.
    """

    move: str
    end: str
    resume: ResumeTemplate | None = None


# Each harness's way out, which every session-derived Cleanup blocker and
# ``work show`` read, and its resume command: a harness adds its entry here,
# and one without an entry is given ``ANY_SESSION_EXIT``, which has none.
SESSION_EXITS: Mapping[Harness, SessionExit] = {
    # ExitWorktree(keep) returns only a session EnterWorktree brought here; a
    # shell cd back into the checkout the session started in places it there
    # without its run (ADR 0074); a session started here can only be ended.
    "claude-code": SessionExit(
        move="run ExitWorktree with action: keep in that session if "
        "EnterWorktree brought it here, or cd its shell back to the checkout "
        "it started in if it came by cd (leaving any Agent Run here)",
        end="end that session",
        # Claude Code files a conversation under the Worktree it entered, so
        # the resume starts there; it continues the session's Agent Run
        # (ADR 0053).
        resume=ResumeTemplate(
            ("claude", "--resume", RESUME_SESSION_ID), from_directory=True
        ),
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
        # An Orphaned Agent Run's thread resumes with its directory as -C,
        # which continues the conversation alone, not the run.
        resume=ResumeTemplate(
            ("codex", "resume", RESUME_SESSION_ID, "-C", RESUME_DIRECTORY)
        ),
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
        # The session resumes once a server runs it again; its run continues
        # only by an explicit work start (ADR 0090).
        resume=ResumeTemplate(
            ("opencode", RESUME_DIRECTORY, "--session", RESUME_SESSION_ID)
        ),
    ),
}


ANY_SESSION_EXIT = SessionExit(
    move="move that session out of this Worktree with its harness's own tool",
    end="end that session",
)


def session_exit(harness: Harness) -> SessionExit:
    """The way out of a Worktree for a session of ``harness``."""
    return SESSION_EXITS.get(harness, ANY_SESSION_EXIT)


def resume_template(harness: Harness) -> ResumeTemplate | None:
    """How a session of ``harness`` is resumed, or None for a harness without one."""
    return session_exit(harness).resume


def listed_subagents(count: int) -> str:
    """``1 sub-agent listed as working``: how many sub-agents a session lists."""
    return f"{counted(count, 'sub-agent')} listed as working"


def named_subagents(agents: Sequence[str]) -> str:
    """``1 sub-agent listed as working (G)``: the sub-agents a session lists, by id."""
    return f"{listed_subagents(len(agents))} ({', '.join(agents)})"


def unreported_subagent_stop(harness: Harness) -> str:
    """Why a sub-agent listed as working may not be, and the way out if none is.

    A session keeps a sub-agent in its live set until the harness's
    ``SubagentStop``, or until the session ends, starts again or its Host
    Process is gone. Some harnesses end a sub-agent without one: a Codex
    child interrupted through its own thread (#374), and a Claude Code
    sub-agent its session stops with ``TaskStop``, or one a headless SDK
    interrupt kills (#419). So the sentence names neither mechanism, covers a stopped
    sub-agent as well as an interrupted one, and names the harness's way to
    end the session rather than guessing which sub-agent is still working.
    """
    return (
        f"Dashpot lists a sub-agent until {HARNESS_DISPLAY[harness]} reports "
        f"that it stopped, which one that was stopped or interrupted may "
        f"never do, so if none is still working, "
        f"{session_exit(harness).end.replace('{session_id}', '<session id>')}"
    )


def forget_subagents_command(harness: Harness, session_id: str) -> str:
    """The command that forgets the sub-agents an ended session still lists.

    It names the harness, so a session id two harnesses share is not refused.
    """
    return shell_command(
        "dashpot", "work", "forget-subagents", session_id, "--harness", harness
    )


def ended_session_subagent_stop(harness: Harness, session_id: str) -> str:
    """Why a sub-agent an ended session lists may not be working, and the way out.

    An ended record keeps the sub-agents its session left working until each
    ``SubagentStop`` or until the Host Process is gone (ADR 0095). Some
    sub-agents never publish one: a Codex worker that ends with its deleted
    lead, a Codex child interrupted through its own thread (#374), and a
    Claude Code sub-agent its session stops with ``TaskStop``, or one a
    headless SDK interrupt kills (#419). So the sentence names none of those
    mechanisms, covers a stopped sub-agent as well as an interrupted one or
    one that ended with its session, and names the command that forgets them
    once a person has checked.
    """
    return (
        f"Dashpot lists a sub-agent of an ended session until "
        f"{HARNESS_DISPLAY[harness]} reports that it stopped or the "
        f"session's process exits, which one that was stopped, was "
        f"interrupted or ended with its session may never do, so if none is "
        f"still working, run {forget_subagents_command(harness, session_id)}"
    )
