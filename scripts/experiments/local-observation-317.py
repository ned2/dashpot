"""Measure local command spans over a disposable two-Worktree Project.

Run with this checkout's locked environment. To compare a fixed baseline,
export its src directory with git archive and pass --source-root to that src.
Fixtures and child processes are created before measurement; no GitHub call,
remote fetch, or change to a real Project is made.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--refreshes", type=int, default=5)
    args = parser.parse_args()
    if args.source_root is not None:
        sys.path.insert(0, str(args.source_root.resolve()))

    from dashpot.core.event_log import EventLog, use_event_log
    from dashpot.core.runtime_events import (
        CommandAttributes,
        ProcessIdentity,
        ProcessStart,
        SpanEnded,
    )
    from dashpot.observation.collect import create_project_collector
    from dashpot.project.workspace import ResolvedProject
    from dashpot.sessions.agents import observe_agent_runs
    from dashpot.sessions.hook_records import session_directory, write_hook_record
    from dashpot.sessions.processes import ProcessPresent, host_process_lookup

    with tempfile.TemporaryDirectory(prefix="dashpot-317-") as temporary:
        root = Path(temporary) / "main"
        linked = Path(temporary) / "feature"
        root.mkdir()

        def git(*words: str) -> None:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.com",
                    *words,
                ],
                cwd=root,
                capture_output=True,
                check=True,
            )

        def commit(text: str, message: str) -> None:
            (root / "app").write_text(text)
            git("add", "app")
            git("commit", "-qm", message)

        git("init", "-q", "-b", "main")
        commit("one\n", "seed")
        git("checkout", "-qb", "feature")
        commit("one\ntwo\n", "two")
        commit("one\ntwo\nthree\n", "three")
        git("checkout", "-q", "main")
        git("merge", "--squash", "-q", "feature")
        git("commit", "-qm", "squash")
        commit("one\ntwo\nthree\nfour\n", "advance")
        (root / ".dashpot").mkdir()
        (root / ".dashpot/config.json").write_text(
            json.dumps(
                {
                    "projectId": "project:measurement",
                    "displayLabel": "Measurement",
                    "repositoryId": "repository:measurement",
                    "issueSource": {"kind": "markdown", "path": "issues"},
                }
            )
        )
        (root / "issues").mkdir()
        git("add", ".dashpot/config.json")
        git("commit", "-qm", "configure")
        git("worktree", "add", "-q", str(linked), "feature")
        project = ResolvedProject(
            "project:measurement",
            "Measurement",
            "repository:measurement",
            ("measurement",),
            (str(root),),
            str(root),
        )
        collector = create_project_collector(project)
        children: list[subprocess.Popen[str]] = []
        try:
            for index in range(3):
                child = subprocess.Popen(
                    [sys.executable, "-c", "import sys; sys.stdin.read()"],
                    stdin=subprocess.PIPE,
                    text=True,
                )
                children.append(child)
                process = host_process_lookup(child.pid)
                assert isinstance(process, ProcessPresent)
                write_hook_record(
                    {
                        "version": 2,
                        "harness": "codex",
                        "sessionId": f"measurement-{index}",
                        "state": "waiting",
                        "cwd": str(root),
                        "repositoryRoot": str(root),
                        "branch": "main",
                        "event": "Stop",
                        "lastActivityAt": "2026-10-04T00:00:00Z",
                        "sessionProcess": process.identity.as_record(),
                    },
                    session_directory(root),
                )
            log = EventLog(
                None,
                identity=ProcessIdentity(run_id="0" * 32, kind="dashboard"),
                level="full",
                facts=ProcessStart,
                keep_recent=10000,
            )
            rows = []
            for refresh in range(args.refreshes):
                log.recent.clear()
                with use_event_log(log):
                    inventory = collector.observe_targets()
                    runs, diagnostics = observe_agent_runs(
                        {project.project_id: inventory.targets},
                        Path(temporary) / "global",
                    )
                assert not inventory.diagnostics and not diagnostics
                assert len(runs) == 3
                commands: Counter[str] = Counter()
                programs: Counter[str] = Counter()
                for event in log.recent:
                    body = event.body
                    if isinstance(body, SpanEnded) and body.span_name == "command":
                        attributes = body.attributes
                        assert isinstance(attributes, CommandAttributes)
                        program = attributes.program
                        programs[program] += 1
                        commands[
                            f"{program} {attributes.subcommand or ''}".strip()
                        ] += 1
                answers = {
                    branch.name: [
                        branch.unintegrated_commits,
                        branch.content_integrated,
                    ]
                    for branch in inventory.branches
                }
                rows.append(
                    {
                        "refresh": refresh,
                        "programs": dict(programs),
                        "commands": dict(commands),
                        "integration": answers,
                    }
                )
            print(
                json.dumps(
                    {
                        "worktrees": 2,
                        "branches": 2,
                        "hostProcesses": 3,
                        "refreshes": rows,
                    },
                    indent=2,
                )
            )
        finally:
            for child in children:
                child.communicate(timeout=5)


if __name__ == "__main__":
    main()
