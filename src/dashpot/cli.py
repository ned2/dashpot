"""Define the ``dashpot`` command line and state every refusal on one line."""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Iterable, Sequence
from contextvars import ContextVar
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
from .core.event_log import DASHBOARD_KIND, EventLog, EventLogDestination
from .core.model import Harness
from .core.worktree_paths import worktree_root
from .event_logs import open_event_log, working_directory
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
    start_issue_work,
    stop_issue_work,
)
from .ui.app import DashpotApp

USAGE_EXIT_CODE = 2
# The default command's flags that print instead of opening the dashboard.
HEADLESS_FLAGS = frozenset({"--json", "--compact-json"})
INFORMATION_FLAGS = frozenset({"--help", "-h", "--version"})
# The Event Log of the command line's own process, while ``main`` runs it.
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
    """List active Issue work at this worktree."""
    _report(show_issue_work(Path.cwd().resolve()))
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
    headless snapshot, help or the version; that is read from the tokens
    before parsing, since the dashboard's Event Log is its own file.
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
    if HEADLESS_FLAGS.intersection(tokens):
        return "command:observe", "observe"
    return DASHBOARD_KIND, None


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
    # orderly exit, Ctrl-C among them, ends the process with its status.
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
