from __future__ import annotations

import json
import uuid
from pathlib import Path, PurePosixPath

from .commands import CommandRunner, run_command
from .project_config import PROJECT_CONFIG_NAME
from .repository import (
    github_repo_from_remote,
    observe_github_repository_identity,
    worktree_root,
)


STATE_IGNORE_RULE = ".dashpot/state/"


def initialize_project(
    current: Path,
    *,
    markdown_path: str | None = None,
    timeout: float = 10,
    runner: CommandRunner = run_command,
) -> list[str]:
    """Write a new Project configuration and return messages to display."""
    try:
        root = worktree_root(current)
    except RuntimeError as exc:
        raise RuntimeError(
            "dashpot init must run inside a Git repository"
        ) from exc
    config_path = root / PROJECT_CONFIG_NAME
    if config_path.is_file():
        raise RuntimeError(f"already configured: {config_path}")
    reference = github_repo_from_remote(root)
    if markdown_path is not None:
        parsed = PurePosixPath(markdown_path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise RuntimeError("--markdown path must be repository-relative")
        repository_id = f"repository:{uuid.uuid4()}"
        display_label = root.name
        issue_source: dict[str, str] = {"kind": "markdown", "path": markdown_path}
    elif reference is not None:
        repository_id, observed_reference = observe_github_repository_identity(
            root, reference, timeout, runner
        )
        display_label = observed_reference.rpartition("/")[2]
        issue_source = {"kind": "github"}
    else:
        raise RuntimeError(
            f"{root} has no GitHub origin remote; pass --markdown PATH to "
            f"declare a Local Issue Markdown source"
        )
    config = {
        "projectId": f"project:{uuid.uuid4()}",
        "displayLabel": display_label,
        "repositoryId": repository_id,
        "issueSource": issue_source,
    }
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    messages = [f"created {config_path}"]
    if not _ignores_state_directory(root, runner):
        messages.append(
            f"add '{STATE_IGNORE_RULE}' to {root / '.gitignore'} so local "
            f"runtime state never dirties the worktree"
        )
    return messages


def _ignores_state_directory(root: Path, runner: CommandRunner) -> bool:
    try:
        result = runner(
            ["git", "check-ignore", "-q", f"{STATE_IGNORE_RULE}probe"],
            root,
            5,
        )
    except (OSError, RuntimeError):
        return False
    return result.returncode == 0
