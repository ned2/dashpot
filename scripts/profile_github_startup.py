"""Measure live GitHub startup through the real headless Textual dashboard."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import threading
import time
import types
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

INVOKED = time.perf_counter()
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def source_at(ref: str) -> types.ModuleType:
    """Load current source or a baseline revision without changing the checkout."""
    if ref == "current":
        import dashpot.github_issues as module

        return module
    code = subprocess.check_output(
        ["git", "show", f"{ref}:src/dashpot/github_issues.py"], cwd=ROOT, text=True
    )
    module = types.ModuleType("dashpot.benchmark_baseline")
    sys.modules[module.__name__] = module
    exec(compile(code, "baseline_github_issues.py", "exec"), module.__dict__)
    return module


def node_count(value: object) -> int:
    """Count returned connection entries, including nested connection entries."""
    if isinstance(value, dict):
        return sum(
            (len(child) if key == "nodes" and isinstance(child, list) else 0)
            + node_count(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return sum(node_count(child) for child in value)
    return 0


async def sample(args: argparse.Namespace) -> dict[str, Any]:
    """Measure one process with a private copy of its Snapshot Seed."""
    module = source_at(args.ref)
    from dashpot.app import DashpotApp
    from dashpot.cli import ObservationOptions, create_collector
    from dashpot.collect import ObservationOutcome, ObservationTicket, ProjectCollector
    from dashpot.commands import CommandResult, CommandRunner, run_command
    from dashpot.github import GitHubGateway
    from dashpot.github_issue_snapshot import (
        GitHubIssueSnapshotRecord,
        GitHubIssueSnapshotStore,
    )
    from dashpot.github_issues import GitHubIssuesSource
    from dashpot.observation_store import StoreChange, WorkspaceObservationStore
    from dashpot.project_config import load_project_config

    events: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    lock = threading.Lock()

    def stamp(name: str) -> None:
        with lock:
            events.append({"event": name, "seconds": time.perf_counter() - INVOKED})

    def measured_runner(
        command: Sequence[str], cwd: Path, timeout: float
    ) -> CommandResult:
        start = time.perf_counter() - INVOKED
        result = run_command(command, cwd, timeout)
        end = time.perf_counter() - INVOKED
        query = next((s[6:] for s in command if s.startswith("query=")), "")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {}
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        data = data if isinstance(data, dict) else {}
        with lock:
            requests.append(
                {
                    "query": query.split("(")[0].strip() if query else command[2],
                    "start": start,
                    "end": end,
                    "seconds": end - start,
                    "bytes": len(result.stdout.encode()),
                    "nodes": node_count(data),
                    "rateLimit": data.get("rateLimit"),
                    "returncode": result.returncode,
                }
            )
        return result

    original_init = GitHubGateway.__init__

    def gateway_init(
        self: GitHubGateway,
        root: Path,
        *,
        timeout: float = 10,
        runner: CommandRunner = run_command,
    ) -> None:
        original_init(self, root, timeout=timeout, runner=measured_runner)

    with tempfile.TemporaryDirectory(prefix="dashpot-benchmark-") as directory:
        store = GitHubIssueSnapshotStore(Path(directory))
        if args.seed:
            record = GitHubIssueSnapshotRecord.model_validate(
                json.loads(args.seed.read_text())
            )
            marks = record.pull_request_marks
            if args.state == "pending":
                record = record.model_copy(
                    update={
                        "pull_request_marks": marks.model_copy(
                            update={
                                "candidate": marks.settled,
                                "settled": None,
                            }
                        )
                    }
                )
            elif args.state == "future-issue":
                record = record.model_copy(
                    update={"high_water": "2099-01-01T00:00:00Z"}
                )
            elif args.state == "future-pr":
                record = record.model_copy(
                    update={
                        "pull_request_marks": marks.model_copy(
                            update={
                                "candidate": "2099-02-01T00:00:00Z",
                                "settled": "2099-01-01T00:00:00Z",
                            }
                        )
                    }
                )
            if args.state != "no-seed":
                store.replace(record)

        def make_source(root: Path, **kwargs: object) -> GitHubIssuesSource:
            kwargs["snapshot_store"] = store
            return cast("GitHubIssuesSource", module.GitHubIssuesSource(root, **kwargs))

        ready = DashpotApp.on_ready

        def timed_ready(self: DashpotApp) -> None:
            stamp("on_ready")
            ready(self)

        with (
            ExitStack() as patches,
            patch.object(GitHubGateway, "__init__", gateway_init),
            patch("dashpot.collect.GitHubIssuesSource", make_source),
            patch.object(DashpotApp, "on_ready", timed_ready),
        ):
            stamp("imports")
            coordinator = create_collector(ObservationOptions(refresh_seconds=0))
            stamp("collector")
            observe = coordinator.observe
            publish = coordinator.publish

            def timed_observe(ticket: ObservationTicket) -> ObservationOutcome:
                stamp(f"start:{ticket.key.kind}")
                result = observe(ticket)
                stamp(f"end:{ticket.key.kind}")
                return result

            def timed_publish(
                store: WorkspaceObservationStore, *, elapsed_ms: int | None = None
            ) -> list[StoreChange]:
                stamp("start:publication")
                result = publish(store, elapsed_ms=elapsed_ms)
                stamp("end:publication")
                return result

            patches.enter_context(patch.object(coordinator, "observe", timed_observe))
            patches.enter_context(patch.object(coordinator, "publish", timed_publish))
            app = DashpotApp(coordinator, refresh_seconds=0)
            async with asyncio.timeout(90), app.run_test(size=(160, 50)):
                while not app.dashboard.queue_table().row_count and app.in_flight:
                    await asyncio.sleep(0.001)
                stamp(
                    "first-row" if app.dashboard.queue_table().row_count else "no-row"
                )
                while app.in_flight:
                    await asyncio.sleep(0.001)
                checkpoint = app.store.checkpoint()
                statuses = [
                    (p.status, len(p.snapshot.issues) if p.snapshot else 0)
                    for p in checkpoint.projects
                ]
                if args.output_seed:
                    source = cast(
                        "ProjectCollector",
                        coordinator.collectors[checkpoint.projects[0].project_id],
                    ).source
                    result = await asyncio.to_thread(source.refresh)
                    if result.status != "fresh":
                        raise RuntimeError("Cannot prepare a settled Snapshot Seed")
                    config = load_project_config(Path.cwd())
                    args.output_seed.write_text(
                        store.path(config.repository_id).read_text()
                    )
        return {
            "ref": args.ref,
            "state": args.state,
            "events": events,
            "requests": requests,
            "statuses": statuses,
        }


def main() -> None:
    """Print timing evidence while making only read-only GitHub requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref", default="current", help="Git revision of the Issue Source, or current"
    )
    parser.add_argument(
        "--state",
        choices=["no-seed", "settled", "pending", "future-issue", "future-pr"],
        default="no-seed",
    )
    parser.add_argument(
        "--seed",
        type=Path,
        help="Copy this Snapshot Seed into an isolated temporary store",
    )
    parser.add_argument(
        "--output-seed",
        type=Path,
        help="Write a live Snapshot Seed after its confirmation refresh",
    )
    args = parser.parse_args()
    if args.state != "no-seed" and args.seed is None:
        parser.error("--seed is required for a seeded startup")
    print(json.dumps(asyncio.run(sample(args))))


if __name__ == "__main__":
    main()
