"""Gather the command groups on the root App, and run one command line to its exit status.

``main`` tells the process kind a command line runs as before dispatch,
opens that process's Event Log, and maps every outcome to an exit status:
every command failure is one ``dashpot: <message>`` line on stderr and
exit 2.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from cyclopts import App, CycloptsError, Parameter

from ..core.errors import DashpotError, failure_text
from ..core.event_log import (
    DASHBOARD_KIND,
    EventLogDestination,
    use_event_log,
    working_directory,
)
from ..event_logs import open_event_log
from . import events, init, integrate, observe, sources, work, worktrees
from .shared import EVENT_LOG, USAGE_EXIT_CODE

# The default command's flags that print instead of opening the dashboard.
HEADLESS_FLAGS = frozenset({"--json", "--compact-json"})
INFORMATION_FLAGS = frozenset({"--help", "-h", "--version"})


def _format_usage_error(error: CycloptsError) -> str:
    # One line in the same voice as application errors, without a usage dump.
    return f"dashpot: {error}"


app = App(
    name="dashpot",
    help="Passively observe Issues, repositories, and agent runs.",
    # Dashpot's flags have no negative forms and its help lists no defaults
    # for them, so the generated --no-* and --empty-* spellings are dropped.
    default_parameter=Parameter(negative=()),
    error_formatter=_format_usage_error,
)
app.default(observe.observe)
app.command(init.init)
app.command(work.work)
app.command(events.events)
app.command(sources.issue)
app.command(sources.pr)
app.command(worktrees.worktree)
app.command(worktrees.branch)
app.command(integrate.integrate, usage=integrate.INTEGRATE_USAGE)


def process_kind(tokens: Sequence[str]) -> tuple[str, str | None]:
    """The process kind a command line runs as, and its subcommand without arguments.

    The default command opens the dashboard unless it is asked for a
    headless snapshot, help or the version, or its arguments are refused;
    that is read from the tokens before dispatch, since the dashboard's
    Event Log is its own file.
    """
    try:
        chain, _apps, _unused = app.parse_commands(list(tokens))
    except CycloptsError:
        chain = ()
    words = [word for word in chain if not word.startswith("-")]
    if words:
        return f"command:{'-'.join(words)}", " ".join(words)
    if INFORMATION_FLAGS.intersection(tokens):
        return "command:help", "help"
    if HEADLESS_FLAGS.intersection(tokens) or not _opens_dashboard(tokens):
        return "command:observe", "observe"
    return DASHBOARD_KIND, None


def _opens_dashboard(tokens: Sequence[str]) -> bool:
    # Dispatch parses again and reports the refusal; this parse stays quiet.
    try:
        app.parse_args(list(tokens), exit_on_error=False, print_error=False)
    except (CycloptsError, DashpotError, ValueError):
        return False
    return True


def main(
    argv: Sequence[str] | None = None,
    *,
    event_log: EventLogDestination | None = None,
) -> int:
    """Run the Dashpot command line and return its exit code.

    ``event_log`` is where this process's Runtime Events go; by default the
    configured checkout containing the working directory, else the
    machine-local fallback.
    """
    tokens = list(sys.argv[1:] if argv is None else argv)
    kind, subcommand = process_kind(tokens)
    log = open_event_log(
        kind,
        working_directory=working_directory(),
        destination=event_log,
        subcommand=subcommand,
    )
    log.start()
    active = EVENT_LOG.set(log)
    # A traceback leaves no ``process.end``: a missing end is a crash. An
    # orderly exit ends the process with its status; Cyclopts turns Ctrl-C
    # into one, exit 130, and a dashboard whose handler raised exits 1 once
    # Textual has printed the traceback.
    try:
        # The external commands and GitHub requests this invocation runs are
        # recorded as its spans.
        with use_event_log(log):
            code = _dispatch(tokens)
    except SystemExit as stop:
        log.end(exit_status(stop))
        raise
    else:
        log.end(code)
    finally:
        EVENT_LOG.reset(active)
        log.close()
    return code


def exit_status(stop: SystemExit) -> int:
    """The status a process leaving by ``SystemExit`` exits with."""
    if stop.code is None:
        return 0
    return stop.code if isinstance(stop.code, int) else 1


def _dispatch(tokens: list[str]) -> int:
    try:
        # Cyclopts would exit 1 on a usage error and exit for us on success;
        # Dashpot keeps exit 2 for every failure and returns the code instead.
        result = app(
            tokens,
            exit_on_error=False,
            result_action="return_int_as_exit_code_else_zero",
        )
    except CycloptsError:
        return USAGE_EXIT_CODE
    except DashpotError as exc:
        # The stated error contract: every command failure is one
        # ``dashpot: <message>`` line on stderr and exit 2.
        print(f"dashpot: {failure_text(exc)}", file=sys.stderr)
        return USAGE_EXIT_CODE
    return int(result)
