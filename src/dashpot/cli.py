from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .app import DashpotApp
from .collect import WorkspaceCollector
from .init import initialize_project
from .model import RepositoryAnchor, Workspace, to_jsonable
from .observation_store import WorkspaceObservationStore
from .project_config import PROJECT_CONFIG_NAME
from .repository import worktree_root
from .workspace import (
    default_workspace_config,
    load_workspaces,
    merge_workspaces,
    resolve_workspace_projects,
)


def parse_workspace_argument(value: str) -> Workspace:
    if "=" in value:
        name, raw_root = value.split("=", 1)
    else:
        raw_root = value
        name = Path(raw_root).expanduser().resolve().name
    if not name.strip() or not raw_root.strip():
        raise argparse.ArgumentTypeError("workspace must be PATH or NAME=PATH")
    return Workspace(
        name.strip(),
        (RepositoryAnchor(str(Path(raw_root).expanduser().resolve())),),
    )


def non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def positive_float(value: str) -> float:
    parsed = non_negative_float(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashpot",
        description="Passively observe Issues, repositories, and agent runs.",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        type=parse_workspace_argument,
        default=[],
        metavar="[NAME=]PATH",
        help=(
            "repository anchor in a named Workspace (repeatable); defaults to "
            "the Dashpot workspace config"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "Dashpot workspace config; by default, observe the configured current "
            "project or fall back to the standard workspace config"
        ),
    )
    parser.add_argument("--timeout", type=positive_float, default=10.0)
    parser.add_argument(
        "--refresh-seconds",
        type=non_negative_float,
        default=15.0,
        help="automatic refresh period; zero disables polling",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="override the Codex hook record directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="collect once and print the headless snapshot instead of opening the TUI",
    )
    parser.add_argument(
        "--compact-json",
        action="store_true",
        help="omit JSON indentation (implies --json)",
    )
    subparsers = parser.add_subparsers(dest="command")
    init = subparsers.add_parser(
        "init",
        help=f"write {PROJECT_CONFIG_NAME} for the current repository",
        description=(
            "Configure the current repository as a Dashpot Project. With a "
            "GitHub origin remote the Issue Source defaults to GitHub and the "
            "durable repository identity is resolved through the "
            "authenticated gh CLI."
        ),
    )
    init.add_argument(
        "--markdown",
        metavar="PATH",
        help=(
            "declare a Local Issue Markdown source at this repository-"
            "relative path instead of GitHub Issues"
        ),
    )
    return parser


def create_collector(args: argparse.Namespace) -> WorkspaceCollector:
    if args.workspace:
        workspaces = merge_workspaces(args.workspace)
    elif args.config is not None:
        workspaces = load_workspaces(args.config.expanduser())
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
    resolution = resolve_workspace_projects(workspaces, timeout=args.timeout)
    return WorkspaceCollector(
        resolution.projects,
        timeout=args.timeout,
        state_dir=args.state_dir.expanduser() if args.state_dir else None,
        diagnostics=resolution.diagnostics,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            for message in initialize_project(
                Path.cwd().resolve(),
                markdown_path=args.markdown,
                timeout=args.timeout,
            ):
                print(message)
            return 0
        collector = create_collector(args)
        if args.json or args.compact_json:
            store = WorkspaceObservationStore(collector.refresh())
            print(
                json.dumps(
                    to_jsonable(store.checkpoint()),
                    indent=None if args.compact_json else 2,
                )
            )
        else:
            DashpotApp(collector, refresh_seconds=args.refresh_seconds).run()
    except RuntimeError as exc:
        print(f"dashpot: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
