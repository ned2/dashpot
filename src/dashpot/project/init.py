"""Write a new Project configuration into the current Repository."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..core.commands import CommandRunner, run_command
from ..core.errors import DashpotError
from ..core.git import Git, GitError
from ..core.pydantic import repository_relative
from ..core.worktree_paths import worktree_root
from ..github.github_repository import (
    github_repo_from_remote,
    observe_github_repository_identity,
)
from .project_config import PROJECT_CONFIG_NAME


class InitError(DashpotError):
    """A ``dashpot init`` refused before writing the Project configuration."""


def initialize_project(
    current: Path,
    *,
    markdown_path: str | None = None,
    timeout: float = 10,
    runner: CommandRunner = run_command,
    git: Git | None = None,
) -> list[str]:
    """Write a new Project configuration and return messages to display.

    ``git`` answers every Git question; ``runner`` runs only ``gh``, which
    keeps its own seam.
    """
    adapter = git if git is not None else Git(current, timeout)
    try:
        root = worktree_root(current, adapter)
    except GitError as exc:
        raise InitError("dashpot init must run inside a Git repository") from exc
    adapter = adapter.at(root)
    config_path = root / PROJECT_CONFIG_NAME
    if config_path.is_file():
        raise InitError(f"already configured: {config_path}")
    reference = github_repo_from_remote(root, adapter)
    if markdown_path is not None:
        try:
            repository_relative(markdown_path)
        except ValueError as exc:
            raise InitError(f"--markdown path {exc}") from exc
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
        raise InitError(
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
    return [f"created {config_path}"]
