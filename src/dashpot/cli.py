from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .app import DashpotApp
from .collect import (
    WorkspaceCollector,
    default_workspace_config,
    discover_project_targets,
    load_workspace_entries,
)
from .model import WorkspaceEntry, to_jsonable


def parse_workspace_argument(value: str) -> WorkspaceEntry:
    if "=" in value:
        name, raw_root = value.split("=", 1)
    else:
        raw_root = value
        name = Path(raw_root).expanduser().resolve().name
    if not name.strip() or not raw_root.strip():
        raise argparse.ArgumentTypeError("workspace must be PATH or NAME=PATH")
    return WorkspaceEntry(name.strip(), str(Path(raw_root).expanduser().resolve()))


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
        description="Passively observe TASKS.md work, repositories, and agent runs.",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        type=parse_workspace_argument,
        default=[],
        metavar="[NAME=]PATH",
        help="workspace root (repeatable); defaults to the TASKS.md workspace config",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_workspace_config(),
        help="TASKS.md workspace config used when --workspace is omitted",
    )
    parser.add_argument("--tasks-command", default="tasks")
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
    return parser


def create_collector(args: argparse.Namespace) -> WorkspaceCollector:
    entries: list[WorkspaceEntry] = args.workspace or load_workspace_entries(
        args.config.expanduser()
    )
    targets = discover_project_targets(entries)
    if not targets:
        roots = ", ".join(entry.root for entry in entries)
        raise RuntimeError(f"no TASKS.md projects discovered under: {roots}")
    return WorkspaceCollector(
        targets,
        tasks_command=args.tasks_command,
        timeout=args.timeout,
        state_dir=args.state_dir.expanduser() if args.state_dir else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        collector = create_collector(args)
        if args.json or args.compact_json:
            snapshot = collector.refresh()
            print(
                json.dumps(
                    to_jsonable(snapshot),
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
