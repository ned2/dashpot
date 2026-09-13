"""Exercise each distribution in a fresh environment outside the checkout."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path, input_text: str | None = None) -> str:
    """Run a bounded smoke command and include stderr in any failure."""
    result = subprocess.run(
        args, cwd=cwd, input=input_text, capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError(f"{args!r}: {result.returncode}\n{result.stderr}")
    return result.stdout


async def check_tui(root: Path) -> None:
    """Collect and quit the installed TUI at compact and wide sizes."""
    from textual.widgets import DataTable

    from dashpot.cli import (
        DashpotApp,
        ObservationOptions,
        create_collector,
        create_query_sources,
    )
    from dashpot.model import RepositoryAnchor, Workspace

    for size in ((60, 20), (120, 40)):
        collector = create_collector(
            ObservationOptions(
                workspaces=(Workspace("smoke", (RepositoryAnchor(str(root)),)),),
                refresh_seconds=0,
            ),
            recurring=False,
        )
        app = DashpotApp(
            collector, sources=create_query_sources(collector), refresh_seconds=0
        )
        async with app.run_test(size=size) as pilot:
            async with asyncio.timeout(30):
                while app.query_one("#queue", DataTable).row_count != 1:
                    await pilot.pause(0.05)
            await pilot.press("q")


def check_integrations(root: Path) -> None:
    """Execute installed publishers and preserve unrelated harness settings."""
    from dashpot.integrate import (
        ISSUE_WORK_SKILL_VERSION,
        install_integration,
        integration,
        integration_status,
        issue_work_skill_directory,
        remove_integration,
    )

    assert version("dashpot") == ISSUE_WORK_SKILL_VERSION
    for harness in ("codex", "claude-code"):
        spec = integration(harness)
        config_home = root / "harnesses" / harness / spec.home_name
        config_home.mkdir(parents=True)
        settings = config_home / spec.hooks_file
        unrelated = {"type": "command", "command": "printf unrelated"}
        original = {"hooks": {"Stop": [{"hooks": [unrelated]}]}}
        settings.write_text(json.dumps(original))
        install_integration(harness, config_home)
        first = settings.read_bytes()
        install_integration(harness, config_home)
        assert settings.read_bytes() == first
        skill = issue_work_skill_directory(spec, config_home)
        assert (skill / "references/dispatch.md").is_file()
        assert (skill / "references/recovery.md").is_file()
        document = json.loads(settings.read_text())
        command = document["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        event = {
            "session_id": f"smoke-{harness}",
            "hook_event_name": "SessionStart",
            "cwd": str(root),
        }
        assert (
            run("/bin/sh", "-c", command, cwd=root, input_text=json.dumps(event)) == ""
        )
        records = list((root / ".dashpot/state/sessions").rglob("*.json"))
        assert any(
            json.loads(p.read_text())["sessionId"] == event["session_id"]
            for p in records
        )
        messages = integration_status(harness, config_home, current=root, environ={})
        assert not any("publisher missing" in message for message in messages)
        event["hook_event_name"] = "SessionEnd"
        assert (
            run("/bin/sh", "-c", command, cwd=root, input_text=json.dumps(event)) == ""
        )
        remove_integration(harness, config_home)
        assert json.loads(settings.read_text()) == original
        assert not (skill / "SKILL.md").exists()


def check_installed(root: Path, expected: str) -> None:
    """Observe a real Local Issue Markdown Project without GitHub access."""
    import dashpot

    assert version("dashpot") == expected
    assert dashpot.__file__ is not None
    assert Path(dashpot.__file__).is_relative_to(Path(sys.prefix))
    binary = str(Path(sysconfig.get_path("scripts")) / "dashpot")
    assert run(binary, "--version", cwd=root).strip() == expected
    assert "--workspace" in run(binary, "--help", cwd=root)
    run("git", "init", "-b", "main", cwd=root)
    (root / ".gitignore").write_text(".dashpot/state/\nharnesses/\nno-gh/\n")
    issues = root / "issues"
    issues.mkdir()
    metadata = {
        "id": "smoke-issue",
        "number": 1,
        "reference": "smoke",
        "state": "open",
        "stateReason": None,
        "labels": [],
        "assignees": [],
        "author": None,
        "relationships": {
            "parent": None,
            "subIssues": [],
            "blockedBy": [],
            "blocking": [],
        },
        "issueType": None,
        "milestone": None,
        "createdAt": None,
        "updatedAt": None,
        "closedAt": None,
    }
    (issues / "one.md").write_text(
        "---\n" + json.dumps(metadata) + "\n---\n# Installed Issue\n"
    )
    no_gh = root / "no-gh"
    no_gh.mkdir()
    marker = no_gh / "called"
    gh = no_gh / "gh"
    gh.write_text('#!/bin/sh\ntouch "$(dirname "$0")/called"\nexit 127\n')
    gh.chmod(0o755)
    os.environ["PATH"] = str(no_gh) + os.pathsep + os.environ["PATH"]
    os.environ["DASHPOT_STATE_DIR"] = str(root / ".dashpot/state/fallback")
    run(binary, "init", "--markdown", "issues", cwd=root)
    run("git", "add", ".gitignore", ".dashpot/config.json", "issues", cwd=root)
    run(
        "git",
        "-c",
        "user.name=Smoke",
        "-c",
        "user.email=smoke@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-m",
        "Smoke fixture",
        cwd=root,
    )
    snapshot = json.loads(run(binary, "--json", cwd=root))
    project = snapshot["projects"][0]["snapshot"]
    assert project["issueSourceStatus"] == "fresh"
    assert project["targetStatus"] == "fresh"
    assert project["issues"][0]["title"] == "Installed Issue"
    issue = json.loads(run(binary, "issue", "show", "1", "--json", cwd=root))
    assert issue["id"] == "smoke-issue"
    asyncio.run(check_tui(root))
    check_integrations(root)
    assert not marker.exists(), "Local Issue Markdown invoked gh"
    assert run("git", "status", "--porcelain", cwd=root) == ""
    print(f"Installed {expected}: CLI, Project, TUI, publishers and removal passed")


def main() -> None:
    """Install each archive separately using only declared runtime dependencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="*")
    parser.add_argument("--installed", metavar="VERSION")
    options = parser.parse_args()
    if options.installed:
        check_installed(Path.cwd(), options.installed)
        return
    if not options.archives:
        parser.error("provide a wheel and/or source distribution")
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Install uv before running the artifact smoke test")
    for artifact in options.archives:
        with TemporaryDirectory(prefix="dashpot-install-") as temporary:
            root = Path(temporary)
            environment = root / "tool environment"
            project = root / "project"
            project.mkdir()
            subprocess.run(
                [uv, "venv", "--python", sys.executable, str(environment)], check=True
            )
            python = environment / "bin/python"
            subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    str(artifact.resolve()),
                ],
                check=True,
            )
            clean_environment = {
                key: value
                for key, value in os.environ.items()
                if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
                and not key.startswith(("GIT_", "DASHPOT_"))
            }
            subprocess.run(
                [str(python), str(Path(__file__).resolve()), "--installed", expected],
                cwd=project,
                env=clean_environment,
                check=True,
                timeout=180,
            )


if __name__ == "__main__":
    main()
