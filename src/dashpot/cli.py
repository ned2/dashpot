from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, CycloptsError, Group, Parameter, Token, validators

from .app import DashpotApp
from .collect import ObservationCoordinator
from .errors import DashpotError
from .init import initialize_project
from .integrate import (
    install_integration,
    integration_status,
    remove_integration,
)
from .issue_resolution import describe_issue, show_issue
from .model import RepositoryAnchor, Workspace, to_jsonable
from .project_config import PROJECT_CONFIG_NAME
from .repository import worktree_root
from .work import show_issue_work, start_issue_work, stop_issue_work
from .workspace import (
    default_workspace_config,
    load_workspaces,
    merge_workspaces,
    resolve_workspace_projects,
)
from .worktrees import (
    check_worktree,
    create_issue_worktree,
    describe_removability,
    describe_worktree_plan,
)

Harness = Literal["codex", "claude-code"]

USAGE_EXIT_CODE = 2


@dataclass(frozen=True, slots=True)
class ObservationOptions:
    """Describe what one Dashpot run observes and how patiently."""

    workspaces: tuple[Workspace, ...] = ()
    config: Path | None = None
    timeout: float = 10.0
    refresh_seconds: float = 15.0
    state_dir: Path | None = None


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
        float,
        Parameter(
            validator=validators.Number(gte=0),
            help="automatic refresh period; zero disables polling",
        ),
    ] = 15.0,
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
    collector = create_collector(
        ObservationOptions(
            workspaces=tuple(workspace or ()),
            config=config,
            timeout=timeout,
            refresh_seconds=refresh_seconds,
            state_dir=state_dir,
        )
    )
    if json_output or compact_json:
        # The coordinated barrier publishes every observation and then
        # checkpoints, so headless output stays a single complete snapshot.
        print(
            json.dumps(
                to_jsonable(collector.refresh()),
                indent=None if compact_json else 2,
            )
        )
    else:
        DashpotApp(collector, refresh_seconds=refresh_seconds).run()
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
        "Start, switch, stop, or show explicit Issue work for the agent "
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
        print(json.dumps(found.model_dump(mode="json", by_alias=True), indent=2))
    else:
        _report(describe_issue(found))
    return 0


worktree = App(
    name="worktree",
    help=(
        "Prepare and inspect linked Worktrees for Issue work.\n\n"
        "create is the one command here that mutates: one linked Worktree at "
        "one path outside every Worktree of the Project, on one new Branch, "
        "never fetching (ADR 0008). check is read-only and removes nothing."
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
                "DASHPOT_WORKTREE_ROOT, then the worktreeRoot setting, then "
                "the sibling <checkout>.worktrees/"
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
        print(json.dumps(to_jsonable(plan), indent=2))
    else:
        _report(describe_worktree_plan(plan))
        # Refusals go to stderr straight off the structured field, in the
        # same one-line ``dashpot:`` voice as every other command failure.
        for item in plan.refusals:
            print(f"dashpot: refused: {item}", file=sys.stderr)
    return USAGE_EXIT_CODE if plan.refusals else 0


@worktree.command(name="check")
def worktree_check(
    path: Annotated[Path, Parameter(help="PATH: the Worktree to report on")],
    /,
    *,
    timeout: _Timeout = 10.0,
    json_output: _JsonOutput = False,
) -> int:
    """Report whether a Worktree is removable, and each reason it is not."""
    report = check_worktree(Path.cwd().resolve(), path, timeout=timeout)
    if json_output:
        print(json.dumps(to_jsonable(report), indent=2))
    else:
        _report(describe_removability(report))
    return 0


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
            help="remove exactly the Dashpot hooks",
        ),
    ] = False,
) -> int:
    """Install the opt-in agent lifecycle integration.

    Register, inspect, or remove the opt-in hooks that publish agent session
    lifecycle observations to Dashpot. Nothing is installed without running
    this command.
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


def create_collector(options: ObservationOptions) -> ObservationCoordinator:
    """Resolve the Workspaces one run observes into its coordinator."""
    if options.workspaces:
        workspaces = merge_workspaces(list(options.workspaces))
    elif options.config is not None:
        workspaces = load_workspaces(options.config.expanduser())
    else:
        current = Path.cwd().resolve()
        try:
            project_root = worktree_root(current)
            in_repository = True
        except RuntimeError:
            project_root = current
            in_repository = False
        if (project_root / PROJECT_CONFIG_NAME).is_file():
            workspaces = [
                Workspace(
                    project_root.name,
                    (RepositoryAnchor(str(project_root)),),
                )
            ]
        else:
            inventory = default_workspace_config()
            if in_repository and not inventory.is_file():
                raise RuntimeError(
                    f"this repository has no {PROJECT_CONFIG_NAME}; run "
                    f"'dashpot init' to configure it, or define Workspaces "
                    f"in {inventory}"
                )
            workspaces = load_workspaces(inventory)
    resolution = resolve_workspace_projects(workspaces, timeout=options.timeout)
    return ObservationCoordinator(
        resolution.projects,
        timeout=options.timeout,
        state_dir=options.state_dir.expanduser() if options.state_dir else None,
        diagnostics=resolution.diagnostics,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Dashpot command line and return its exit code."""
    tokens = list(sys.argv[1:] if argv is None else argv)
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
    except (DashpotError, RuntimeError) as exc:
        # The stated error contract: every command failure is one
        # ``dashpot: <message>`` line on stderr and exit 2. The RuntimeError
        # arm stays while bare ``raise RuntimeError`` sites migrate onto
        # DashpotError.
        print(f"dashpot: {exc}", file=sys.stderr)
        return USAGE_EXIT_CODE
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
