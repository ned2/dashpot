"""``dashpot work``: opt the enclosing Agent Session into Issue work."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ..core.model import Harness
from ..core.working_directory import current_directory
from ..sessions.work import (
    forget_session_subagents,
    relocate_issue_work,
    show_issue_work,
    show_session_events,
    start_issue_work,
    stop_issue_work,
)
from ..sessions.worker_assignments import assign_worker, unassign_worker
from .shared import USAGE_EXIT_CODE, Timeout, command_outcome, print_lines

work = App(
    name="work",
    help=(
        "Opt this running agent session into Issue work.\n\n"
        "Start, switch, relocate, stop, or show explicit Issue work for the agent "
        "session enclosing this command, recorded at the current Worktree's "
        ".dashpot/state/; assign a Lead's Workers to Issues; or forget the "
        "sub-agents an ended session still lists."
    ),
)


@work.command
def start(
    reference: Annotated[
        str,
        Parameter(
            help=(
                "Issue Reference, such as a bare Issue Number (12), #12, "
                "owner/repository#12, or a slug"
            )
        ),
    ],
    /,
    *,
    timeout: Timeout = 10.0,
) -> int:
    """Start or switch this session's Issue work."""
    with command_outcome("work start") as outcome:
        print_lines(
            start_issue_work(
                current_directory(), reference, timeout=timeout, outcome=outcome
            )
        )
    return 0


@work.command
def relocate(
    path: Annotated[
        Path,
        Parameter(help="Linked Worktree where this Codex Agent Session will resume"),
    ],
    /,
) -> int:
    """Prepare this Agent Run for a verified sequential Codex resume."""
    with command_outcome("work relocate") as outcome:
        # Read the working directory first: a relative target resolves against
        # it, and it may no longer exist.
        current = current_directory()
        relocate_target = (current / path.expanduser()).resolve()
        outcome.target_path = relocate_target
        print_lines(relocate_issue_work(current, relocate_target, outcome=outcome))
    return 0


@work.command
def stop(
    *,
    session: Annotated[
        str | None,
        Parameter(
            help=(
                "KEY: end the orphaned Agent Run recorded for a session that "
                "is no longer running, instead of this session's own run"
            )
        ),
    ] = None,
) -> int:
    """End this session's active Issue work."""
    with command_outcome("work stop") as outcome:
        print_lines(
            stop_issue_work(current_directory(), session_key=session, outcome=outcome)
        )
    return 0


@work.command(name="forget-subagents")
def forget_subagents(
    session_id: Annotated[
        str,
        Parameter(help="the ended Agent Session whose listed sub-agents to forget"),
    ],
    /,
    *,
    harness: Annotated[
        Harness | None,
        Parameter(help="the session's harness, when two harnesses share its id"),
    ] = None,
) -> int:
    """Forget the sub-agents an ended session still lists as working.

    A session that ends while it lists sub-agents keeps them listed, and
    blocking Worktree Cleanup, until each reports that it stopped or the
    session's process exits. Run this once none of them is still working.
    """
    with command_outcome("work forget-subagents") as outcome:
        print_lines(
            forget_session_subagents(
                current_directory(), session_id, harness=harness, outcome=outcome
            )
        )
    return USAGE_EXIT_CODE if outcome.incomplete else 0


@work.command
def assign(
    reference: Annotated[
        str,
        Parameter(
            help=(
                "Issue Reference the Worker works on, such as a bare Issue "
                "Number (12), #12, owner/repository#12, or a slug"
            )
        ),
    ],
    /,
    *,
    worker: Annotated[
        str,
        Parameter(
            help=(
                "ID: the Worker's Sub-agent identity, as its launch returned it "
                "(a Claude Code agentId, a Codex thread ID, an OpenCode sessionID)"
            )
        ),
    ],
    worktree: Annotated[
        Path,
        Parameter(help="the Worktree the Worker's commands run in"),
    ],
    timeout: Timeout = 10.0,
) -> int:
    """Assign one of this Lead's working Sub-agents to an Issue.

    The assignment joins this session's active Agent Run, whose Issue
    Binding and location stay as they are, and ends with it. The Issue
    shows the Worker's activity while this session's hooks list it as
    working; the assignment alone shows nothing.
    """
    with command_outcome("work assign") as outcome:
        print_lines(
            assign_worker(
                current_directory(),
                reference,
                worker,
                worktree,
                timeout=timeout,
                outcome=outcome,
            )
        )
    return 0


@work.command
def unassign(
    worker: Annotated[
        str, Parameter(help="the Worker's Sub-agent identity, as it was assigned")
    ],
    /,
) -> int:
    """End one Worker Assignment of this session's Agent Run."""
    with command_outcome("work unassign") as outcome:
        print_lines(unassign_worker(current_directory(), worker, outcome=outcome))
    return 0


@work.command
def show() -> int:
    """List active Issue work at this worktree, and this session's recent events.

    The events are the enclosing Agent Session's most recent hook and
    command outcomes, Agent Session and Agent Run changes and failures from
    the Event Log: at most 20, from the last 7 days.
    """
    current = current_directory()
    print_lines(show_issue_work(current))
    print_lines(show_session_events(current))
    return 0
