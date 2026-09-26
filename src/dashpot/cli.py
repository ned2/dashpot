"""Define the ``dashpot`` command line and state every refusal on one line."""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, CycloptsError, Group, Parameter, Token, validators

from .composition import (
    ObservationOptions,
    create_collector,
    create_query_sources,
    refresh_periods,
    run_cleanup,
)
from .core.errors import DashpotError
from .core.event_log import (
    DASHBOARD_KIND,
    EventLog,
    EventLogDestination,
    working_directory,
)
from .core.event_log_files import (
    EventLogError,
    EventSelection,
    describe_event_log_removal,
    describe_runtime_event,
    read_event_logs,
    remove_event_logs,
    repository_event_log_directories,
)
from .core.model import Harness
from .core.runtime_events import RecordedLevel
from .core.worktree_paths import worktree_root
from .event_logs import open_event_log, route_event_log
from .issues.issue_resolution import describe_issue, show_issue
from .project.init import initialize_project
from .project.workspace import RepositoryAnchor, Workspace
from .queries.query_source import configured_query_source
from .queries.source_queries import Lifecycle, PageObservation, QueryRequest
from .repository.cleanup import (
    BranchCleanupRequest,
    CleanupError,
    CleanupPreview,
    CleanupRequest,
    GitCleanupAdapter,
    TargetKind,
    WorktreeCleanupRequest,
    describe_cleanup_report,
)
from .repository.fetch import remote_fetcher
from .repository.worktree_launcher import configure_worktree_launcher
from .repository.worktrees.create import (
    create_issue_worktree,
    describe_worktree_plan,
)
from .repository.worktrees.removability import (
    check_worktree,
    describe_removability,
    linked_worktrees,
)
from .serialization import (
    cleanup_report_document,
    event_log_reading_document,
    event_log_removal_document,
    issue_document,
    list_page_document,
    removability_document,
    render_json,
    snapshot_document,
    worktree_plan_document,
)
from .sessions.integrate import (
    install_integration,
    integration_status,
    remove_integration,
)
from .sessions.work import (
    relocate_issue_work,
    show_issue_work,
    show_session_events,
    start_issue_work,
    stop_issue_work,
)
from .ui.app import DashpotApp

USAGE_EXIT_CODE = 2
# The default command's flags that print instead of opening the dashboard.
HEADLESS_FLAGS = frozenset({"--json", "--compact-json"})
INFORMATION_FLAGS = frozenset({"--help", "-h", "--version"})
# The Event Log of the command line's own process, while ``main`` runs it:
# the hand-off from ``main`` to the ``observe`` command Cyclopts calls, set
# and reset around one dispatch rather than configured for the process.
_EVENT_LOG: ContextVar[EventLog | None] = ContextVar(
    "dashpot_cli_event_log", default=None
)


def parse_workspace_argument(value: str) -> Workspace:
    """Read one ``[NAME=]PATH`` token as a single-anchor Workspace."""
    if "=" in value:
        name, raw_root = value.split("=", 1)
    else:
        raw_root = value
        name = Path(raw_root).expanduser().resolve().name
    if not name.strip() or not raw_root.strip():
        raise ValueError("workspace must be PATH or NAME=PATH")
    return Workspace(
        name.strip(),
        (RepositoryAnchor(str(Path(raw_root).expanduser().resolve())),),
    )


def _convert_workspaces(type_: object, tokens: Sequence[Token]) -> list[Workspace]:
    # Cyclopts hands a list-typed option every repeated token in one call and
    # expects the whole list back; a ValueError here becomes the usage error.
    return [parse_workspace_argument(token.value) for token in tokens]


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

_Timeout = Annotated[
    float,
    Parameter(
        validator=validators.Number(gt=0),
        help="seconds allowed for each external command, such as git and gh",
    ),
]


def _finite_seconds(_type: object, value: float | None) -> None:
    """Refuse a Refresh Period that never elapses."""
    if value is not None and not math.isfinite(value):
        raise ValueError("Must be a finite number of seconds.")


@app.default
def observe(
    *,
    workspace: Annotated[
        list[Workspace] | None,
        Parameter(
            converter=_convert_workspaces,
            n_tokens=1,
            accepts_keys=False,
            help=(
                "[NAME=]PATH: repository anchor in a named Workspace "
                "(repeatable); defaults to the Dashpot workspace config"
            ),
        ),
    ] = None,
    config: Annotated[
        Path | None,
        Parameter(
            help=(
                "Dashpot workspace config; by default, observe the configured "
                "current project or fall back to the standard workspace config"
            )
        ),
    ] = None,
    timeout: _Timeout = 10.0,
    refresh_seconds: Annotated[
        float | None,
        Parameter(
            validator=(validators.Number(gte=0), _finite_seconds),
            help=(
                "seconds between automatic refreshes of Worktrees, Branches and "
                "Agent Sessions, and of a Local Markdown Issue Source; zero "
                "disables them (default: the refresh_seconds setting, else 15)"
            ),
        ),
    ] = None,
    github_refresh_seconds: Annotated[
        float | None,
        Parameter(
            validator=(validators.Number(gte=0), _finite_seconds),
            help=(
                "seconds between automatic refreshes of GitHub Issues and pull "
                "requests; zero disables them (default: the "
                "github_refresh_seconds setting, else 60)"
            ),
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        Parameter(
            help=(
                "override the directory for agent session records outside "
                "configured Projects"
            )
        ),
    ] = None,
    json_output: Annotated[
        bool,
        Parameter(
            name="--json",
            show_default=False,
            help="collect once and print the headless snapshot instead of opening the TUI",
        ),
    ] = False,
    compact_json: Annotated[
        bool,
        Parameter(show_default=False, help="omit JSON indentation (implies --json)"),
    ] = False,
) -> int:
    """Open the TUI for one Project, or print a headless snapshot."""
    headless = json_output or compact_json
    periods = refresh_periods(refresh_seconds, github_refresh_seconds)
    collector = create_collector(
        ObservationOptions(
            workspaces=tuple(workspace or ()),
            config=config,
            timeout=timeout,
            refresh_seconds=periods.local,
            state_dir=state_dir,
        ),
        recurring=not headless,
    )
    if headless:
        # The coordinated barrier publishes every observation and then
        # checkpoints, so headless output stays a single complete snapshot.
        print(render_json(snapshot_document(collector.refresh()), compact=compact_json))
    else:
        sources = create_query_sources(collector)
        DashpotApp(
            collector,
            sources=sources,
            event_log=_EVENT_LOG.get(),
            refresh_seconds=periods.local,
            query_refresh_seconds=periods.query_seconds(sources),
            fetcher=remote_fetcher(timeout),
            cleaner=GitCleanupAdapter(timeout),
            launcher_configuration=configure_worktree_launcher(timeout),
        ).run()
    return 0


@app.command
def init(
    *,
    markdown: Annotated[
        str | None,
        Parameter(
            help=(
                "PATH: declare a Local Issue Markdown source at this "
                "repository-relative path instead of GitHub Issues"
            )
        ),
    ] = None,
    timeout: _Timeout = 10.0,
) -> int:
    """Configure the current repository as a Dashpot Project.

    Writes .dashpot/config.json for the current repository. With a GitHub
    origin remote the Issue Source defaults to GitHub and the durable
    repository identity is resolved through the authenticated gh CLI.
    """
    _report(
        initialize_project(
            Path.cwd().resolve(), markdown_path=markdown, timeout=timeout
        )
    )
    return 0


work = App(
    name="work",
    help=(
        "Opt this running agent session into Issue work.\n\n"
        "Start, switch, relocate, stop, or show explicit Issue work for the agent "
        "session enclosing this command, recorded at the current Worktree's "
        ".dashpot/state/."
    ),
)
app.command(work)


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
    timeout: _Timeout = 10.0,
) -> int:
    """Start or switch this session's Issue work."""
    _report(start_issue_work(Path.cwd().resolve(), reference, timeout=timeout))
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
    relocate_target = path.expanduser().resolve()
    _report(relocate_issue_work(Path.cwd().resolve(), relocate_target))
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
    _report(stop_issue_work(Path.cwd().resolve(), session_key=session))
    return 0


@work.command
def show() -> int:
    """List active Issue work at this worktree, and this session's recent events.

    The events are the enclosing Agent Session's most recent hook and
    command outcomes, Agent Session and Agent Run changes and failures from
    the Event Log: at most 20, from the last 7 days.
    """
    current = Path.cwd().resolve()
    _report(show_issue_work(current))
    _report(show_session_events(current))
    return 0


_IssueHint = Annotated[
    str,
    Parameter(
        help=(
            "Issue Hint: a bare Issue Number (12), #12, a full Issue Reference "
            "such as owner/repository#12, or a Local Issue slug"
        )
    ),
]
_JsonOutput = Annotated[
    bool,
    Parameter(
        name="--json",
        show_default=False,
        help="print the result as JSON with camelCase keys instead of lines",
    ),
]


# ``30m``, ``12h``, ``7d``: an age counted back from now.
_RELATIVE_AGE = re.compile(r"(\d+)([mhd])")
_AGE_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """Read ``--since``: a UTC day, an ISO 8601 instant, or an age such as ``2h``.

    An instant without an offset is UTC, as every Runtime Event is stamped.
    """
    text = value.strip()
    age = _RELATIVE_AGE.fullmatch(text)
    if age is not None:
        moment = now if now is not None else datetime.now(UTC)
        return moment - timedelta(**{_AGE_UNITS[age.group(2)]: int(age.group(1))})
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"{value!r} is not a day (2026-09-27), an instant "
            f"(2026-09-27T14:00:00Z) or an age (30m, 12h, 7d)"
        ) from None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _convert_since(type_: object, tokens: Sequence[Token]) -> datetime:
    return parse_since(tokens[0].value)


def _convert_day(type_: object, tokens: Sequence[Token]) -> date:
    try:
        return date.fromisoformat(tokens[0].value.strip())
    except ValueError:
        raise ValueError(
            f"{tokens[0].value!r} is not a day such as 2026-09-27"
        ) from None


events = App(
    name="events",
    help=(
        "Read or remove the Event Log: the Runtime Events Dashpot records on "
        "this machine.\n\n"
        "Reading merges the Event Log of every Worktree of this Repository "
        "with the machine-local fallback, ordered by time. A dashboard records "
        "its events, including those about other Projects of its Workspace, in "
        "the checkout it was started in, so read them from there. remove "
        "mutates: only this checkout's Event Log files (or the machine-local "
        "fallback's, outside a configured checkout) dated before a day, never "
        "today's or later (ADR 0008)."
    ),
)
app.command(events)


@events.default
def events_read(
    *,
    session: Annotated[
        str | None,
        Parameter(help="ID: only events of this Agent Session Identity"),
    ] = None,
    issue: Annotated[
        str | None,
        Parameter(
            help="ID: only events for this Issue Identity, as 'work show' prints it"
        ),
    ] = None,
    project: Annotated[
        str | None,
        Parameter(
            help=(
                "ID: only events for this Project Identity, the projectId of "
                ".dashpot/config.json"
            )
        ),
    ] = None,
    since: Annotated[
        datetime | None,
        Parameter(
            converter=_convert_since,
            n_tokens=1,
            accepts_keys=False,
            help=(
                "only events from this UTC day (2026-09-27), instant "
                "(2026-09-27T14:00:00Z) or age (30m, 12h, 7d) on"
            ),
        ),
    ] = None,
    level: Annotated[
        RecordedLevel | None,
        Parameter(
            help=(
                "standard: only the events the default level records; full: "
                "every event (the default)"
            )
        ),
    ] = None,
    timeout: _Timeout = 10.0,
    json_output: Annotated[
        bool,
        Parameter(
            name="--json",
            show_default=False,
            help=(
                "print the events as JSON, each under its Event Log field "
                "names, with the lines that could not be read"
            ),
        ),
    ] = False,
) -> int:
    """Read the Event Log of every Worktree of this Repository, oldest event first.

    Lines that cannot be read are reported on stderr and skipped. Only
    .jsonl files are read, so a compressed file is not.
    """
    own = _EVENT_LOG.get()
    reading = read_event_logs(
        repository_event_log_directories(Path.cwd(), timeout=timeout),
        EventSelection(
            session=session,
            issue=issue,
            project=project,
            since=since,
            level=level,
            # This command's own start is not what anyone reads it for.
            exclude_run=None if own is None else own.identity.run_id,
        ),
    )
    if json_output:
        print(render_json(event_log_reading_document(reading)))
        return 0
    if not reading.events:
        print("no matching Runtime Events")
    for event in reading.events:
        print(describe_runtime_event(event))
    for unreadable in reading.unreadable:
        if unreadable.error is not None:
            print(
                f"dashpot: cannot read {unreadable.path}: {unreadable.error}",
                file=sys.stderr,
            )
        if unreadable.lines:
            count = len(unreadable.lines)
            print(
                f"dashpot: skipped {count} unreadable line{'s' if count != 1 else ''} "
                f"in {unreadable.path}",
                file=sys.stderr,
            )
    return 0


@events.command(name="remove")
def events_remove(
    *,
    before: Annotated[
        date,
        Parameter(
            converter=_convert_day,
            n_tokens=1,
            accepts_keys=False,
            help=(
                "DATE: remove the files whose UTC day is before this day "
                "(2026-09-01); today's and later are always kept"
            ),
        ),
    ],
    dry_run: Annotated[
        bool,
        Parameter(
            show_default=False,
            help="report the files that would be removed without removing any",
        ),
    ] = False,
    json_output: _JsonOutput = False,
) -> int:
    """Remove this checkout's Event Log files dated before a day.

    Only files named as the Event Log names them are removed, and none is
    compressed or renamed. Run it from the checkout whose Event Log it is;
    outside every configured checkout it acts on the machine-local fallback.
    """
    destination = route_event_log(working_directory())
    if destination is None:
        raise EventLogError(
            "no Event Log to remove from: no configured checkout encloses this "
            "directory and there is no home directory for the machine-local one"
        )
    removal = remove_event_logs(destination, before, dry_run=dry_run)
    if json_output:
        print(render_json(event_log_removal_document(removal)))
    else:
        _report(describe_event_log_removal(removal))
        for file in removal.files:
            if file.outcome == "failed":
                print(
                    f"dashpot: could not remove {file.path}: {file.error}",
                    file=sys.stderr,
                )
    return 0 if removal.succeeded else USAGE_EXIT_CODE


issue = App(
    name="issue",
    help=(
        "Resolve Issues through the configured Issue Source.\n\n"
        "Source-neutral: the same Issue Hints work for a GitHub Project and a "
        "Local Issue Markdown Project, and nothing is written."
    ),
)
app.command(issue)


@issue.command(name="show")
def issue_show(
    reference: _IssueHint,
    /,
    *,
    timeout: _Timeout = 10.0,
    json_output: _JsonOutput = False,
) -> int:
    """Resolve one Issue Hint and print the Issue Profile."""
    found = show_issue(Path.cwd().resolve(), reference, timeout=timeout)
    if json_output:
        print(render_json(issue_document(found)))
    else:
        _report(describe_issue(found))
    return 0


pr = App(name="pr", help="Query Pull Requests through the configured Project source.")
app.command(pr)


def _list_page(
    kind: Literal["issues", "pull-requests"],
    query: str,
    state: Lifecycle,
    page_size: int,
    cursor: str | None,
    compact: bool,
    timeout: float,
) -> int:
    """Emit one Query Page and the Project Totals its request counted.

    The page's Diagnostics carry what the source reports about itself
    beside it, such as a rate limit running low.
    """
    root = worktree_root(Path.cwd().resolve())
    source = configured_query_source(root, timeout=timeout)
    observation = source.query_page(
        QueryRequest(
            kind=kind, query=query, state=state, page_size=page_size, cursor=cursor
        )
    )
    page = observation.page
    reported = page.model_copy(
        update={"diagnostics": (*page.diagnostics, *source.source_diagnostics())}
    )
    print(
        render_json(
            list_page_document(PageObservation(reported, observation.totals)),
            compact=compact,
        )
    )
    return 0


@issue.command(name="list")
def issue_list(
    *,
    query: str = "",
    state: Lifecycle = "open",
    page_size: Annotated[
        int, Parameter(validator=validators.Number(gte=1, lte=100))
    ] = 50,
    cursor: str | None = None,
    json_output: _JsonOutput = False,
    compact_json: bool = False,
    timeout: _Timeout = 10.0,
) -> int:
    """Query one Issue page; GitHub advanced syntax or Markdown local text.

    ``--state ready`` lists Ready Issues: open, with no Open Blocker.
    """
    return _list_page("issues", query, state, page_size, cursor, compact_json, timeout)


@pr.command(name="list")
def pr_list(
    *,
    query: str = "",
    state: Literal["open", "closed", "all"] = "open",
    page_size: Annotated[
        int, Parameter(validator=validators.Number(gte=1, lte=100))
    ] = 50,
    cursor: str | None = None,
    json_output: _JsonOutput = False,
    compact_json: bool = False,
    timeout: _Timeout = 10.0,
) -> int:
    """Query one Pull Request page using GitHub advanced syntax."""
    return _list_page(
        "pull-requests", query, state, page_size, cursor, compact_json, timeout
    )


worktree = App(
    name="worktree",
    help=(
        "Prepare, inspect, and remove linked Worktrees for Issue work.\n\n"
        "create mutates: one linked Worktree at one path outside every "
        "Worktree of the Project, on one new Branch, never fetching (ADR "
        "0008). remove mutates: one linked Worktree, unforced, after a "
        "read-only preview, and its Branch — locally, at its push remote — "
        "only when asked (ADR 0019, ADR 0054). check "
        "is read-only and removes nothing."
    ),
)
app.command(worktree)


@worktree.command(name="create")
def worktree_create(
    reference: _IssueHint,
    /,
    *,
    base: Annotated[
        str | None,
        Parameter(
            help=(
                "REF: the commit to branch from; defaults to origin/HEAD, else "
                "the one local main or master Branch"
            )
        ),
    ] = None,
    branch: Annotated[
        str | None,
        Parameter(
            help=(
                "NAME: the new Branch; defaults to <number>-<title-slug> "
                "(a Local Issue's slug)"
            )
        ),
    ] = None,
    worktree_root: Annotated[
        Path | None,
        Parameter(
            help=(
                "DIR: the parent directory for the Worktree; defaults to "
                "DASHPOT_WORKTREE_ROOT, then the worktree_root setting, then "
                "the main working tree's sibling <main>.worktrees/"
            )
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(
            show_default=False,
            help="report the path, Branch, base, root, and refusals without creating",
        ),
    ] = False,
    timeout: _Timeout = 10.0,
    json_output: _JsonOutput = False,
) -> int:
    """Create a linked Worktree on a new Branch for an Issue."""
    plan = create_issue_worktree(
        Path.cwd().resolve(),
        reference,
        base=base,
        branch=branch,
        worktree_root_option=worktree_root,
        dry_run=dry_run,
        timeout=timeout,
    )
    if json_output:
        print(render_json(worktree_plan_document(plan)))
    else:
        _report(describe_worktree_plan(plan))
        # Refusals go to stderr straight off the structured field, in the
        # same one-line ``dashpot:`` voice as every other command failure.
        for item in plan.refusals:
            print(f"dashpot: refused: {item}", file=sys.stderr)
    return USAGE_EXIT_CODE if plan.refusals else 0


@worktree.command(name="check")
def worktree_check(
    path: Annotated[
        Path | None,
        Parameter(
            help="PATH: the Worktree to report on; every linked Worktree of the "
            "Repository when omitted",
            show_default=False,
        ),
    ] = None,
    /,
    *,
    timeout: _Timeout = 10.0,
    json_output: _JsonOutput = False,
) -> int:
    """Report whether a Worktree is removable, and each reason it is not."""
    current = Path.cwd().resolve()
    if path is not None:
        report = check_worktree(current, path, timeout=timeout)
        if json_output:
            print(render_json(removability_document(report)))
        else:
            _report(describe_removability(report))
        return 0
    reports = [
        check_worktree(current, worktree, timeout=timeout)
        for worktree in linked_worktrees(current, timeout=timeout)
    ]
    if json_output:
        print(render_json([removability_document(report) for report in reports]))
    elif not reports:
        print("no linked Worktrees in this Repository")
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            _report(describe_removability(report))
    return 0


_DryRun = Annotated[
    bool,
    Parameter(
        show_default=False,
        help="report what would be attempted, in order, without changing anything",
    ),
]


def _cleanup(
    request: CleanupRequest,
    *,
    select: Callable[[CleanupPreview], tuple[str, ...]],
    delete_ignored: bool = False,
    dry_run: bool,
    timeout: float,
    json_output: bool,
) -> int:
    """Preview, select, perform, and report one Cleanup from this checkout."""
    report = run_cleanup(
        request,
        select=select,
        delete_ignored=delete_ignored,
        dry_run=dry_run,
        timeout=timeout,
    )
    if json_output:
        print(render_json(cleanup_report_document(report)))
    else:
        _report(describe_cleanup_report(report))
        for item in report.refusals:
            print(f"dashpot: refused: {item}", file=sys.stderr)
    if report.dry_run:
        return USAGE_EXIT_CODE if report.refusals else 0
    return 0 if report.succeeded else USAGE_EXIT_CODE


branch = App(
    name="branch",
    help=(
        "Delete Branches after a read-only preview.\n\n"
        "delete mutates: only the refs named by its flags — the local Branch, "
        "the Branch at each named remote — each only at the commit the preview "
        "observed, the remote first, never the Integration Branch or a "
        "checked-out Branch (ADR 0019)."
    ),
)
app.command(branch)


@branch.command(name="delete")
def branch_delete(
    name: Annotated[str, Parameter(help="NAME: the Branch, as git branch lists it")],
    /,
    *,
    local: Annotated[
        bool,
        Parameter(
            show_default=False,
            help="delete the local Branch refs/heads/NAME, if it is integrated",
        ),
    ] = False,
    remote: Annotated[
        list[str] | None,
        Parameter(
            help=(
                "REMOTE: delete the Branch at this remote (repeatable), leased on "
                "its Remote-Tracking Branch as of the last fetch"
            ),
            show_default=False,
        ),
    ] = None,
    dry_run: _DryRun = False,
    timeout: _Timeout = 10.0,
    json_output: _JsonOutput = False,
) -> int:
    """Delete the selected refs of a Branch, each at its previewed commit."""
    if not local and not remote:
        raise CleanupError(
            "name at least one target to delete: --local, --remote REMOTE"
        )
    current = Path.cwd().resolve()
    # The identities are spelled out rather than picked from the preview so
    # a ref that is not there is refused by name.
    selected = [f"local:refs/heads/{name}"] if local else []
    selected.extend(f"remote:{each}:refs/heads/{name}" for each in remote or ())
    return _cleanup(
        BranchCleanupRequest(current, name),
        select=lambda _preview: tuple(selected),
        dry_run=dry_run,
        timeout=timeout,
        json_output=json_output,
    )


@worktree.command(name="remove")
def worktree_remove(
    path: Annotated[Path, Parameter(help="PATH: the linked Worktree to remove")],
    /,
    *,
    delete_branch: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "also delete the Worktree's local Branch, once the Worktree is "
                "gone and only if it is integrated"
            ),
        ),
    ] = False,
    delete_remote_branch: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "also delete the Worktree's Branch at the remote a plain git push "
                "reaches, first, leased on its Remote-Tracking Branch as of the "
                "last fetch and only if it is integrated"
            ),
        ),
    ] = False,
    delete_ignored: Annotated[
        bool,
        Parameter(
            show_default=False,
            help=(
                "acknowledge that the Worktree's ignored content (.venv, "
                ".dashpot/state, and the like) is deleted with it"
            ),
        ),
    ] = False,
    dry_run: _DryRun = False,
    timeout: _Timeout = 10.0,
    json_output: _JsonOutput = False,
) -> int:
    """Remove a linked Worktree without force, after a read-only preview."""
    current = Path.cwd().resolve()

    def select(preview: CleanupPreview) -> tuple[str, ...]:
        kinds: set[TargetKind] = {"worktree"}
        if delete_branch:
            kinds.add("local-branch")
        if delete_remote_branch:
            kinds.add("remote-branch")
        chosen = [target for target in preview.targets if target.kind in kinds]
        found = {target.kind for target in preview.targets}
        if (delete_branch or delete_remote_branch) and "local-branch" not in found:
            raise CleanupError(f"{path} has no Branch checked out to delete")
        if delete_remote_branch and "remote-branch" not in found:
            raise CleanupError(
                f"{path}'s Branch has no Remote-Tracking Branch for it at the "
                f"remote a plain git push reaches; fetch, or delete it with "
                f"dashpot branch delete --remote"
            )
        return tuple(target.identity for target in chosen)

    return _cleanup(
        WorktreeCleanupRequest(current, path),
        select=select,
        delete_ignored=delete_ignored,
        dry_run=dry_run,
        timeout=timeout,
        json_output=json_output,
    )


_integrate_action = Group("Action", validator=validators.MutuallyExclusive())


@app.command
def integrate(
    harness: Annotated[Harness, Parameter(help="the agent harness to integrate")],
    /,
    *,
    status: Annotated[
        bool,
        Parameter(
            group=_integrate_action,
            show_default=False,
            help="report integration state without changing anything",
        ),
    ] = False,
    remove: Annotated[
        bool,
        Parameter(
            group=_integrate_action,
            show_default=False,
            help="remove exactly the Dashpot hooks and managed skill",
        ),
    ] = False,
) -> int:
    """Install the opt-in agent lifecycle and Issue-work integration.

    Register, inspect, or remove the opt-in hooks that publish Agent Session
    lifecycle observations and the agent-facing Issue-work skill. Nothing is
    installed without running this command.
    """
    if status:
        messages = integration_status(harness)
    elif remove:
        messages = remove_integration(harness)
    else:
        messages = install_integration(harness)
    _report(messages)
    return 0


def _report(messages: Iterable[str]) -> None:
    for message in messages:
        print(message)


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
    active = _EVENT_LOG.set(log)
    # A traceback leaves no ``process.end``: a missing end is a crash. An
    # orderly exit ends the process with its status; Cyclopts turns Ctrl-C
    # into one, exit 130.
    try:
        code = _dispatch(tokens)
    except SystemExit as stop:
        log.end(exit_status(stop))
        raise
    else:
        log.end(code)
    finally:
        _EVENT_LOG.reset(active)
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
        print(f"dashpot: {exc}", file=sys.stderr)
        return USAGE_EXIT_CODE
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
