"""Write a new Project configuration into the current Repository."""

from __future__ import annotations

import uuid
from contextlib import suppress
from pathlib import Path

from pydantic import ValidationError

from ..core.commands import CommandRunner, run_command
from ..core.errors import DashpotError
from ..core.git import Git, GitError
from ..core.pydantic import describe_validation_error
from ..core.state_paths import PROJECT_CONFIG_PATH
from ..core.worktree_paths import worktree_root
from ..github.github_repository import (
    github_repo_from_remote,
    observe_github_repository_identity,
)
from .project_config import (
    GitHubIssueSourceConfig,
    IssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    ProjectConfig,
)


class InitError(DashpotError):
    """A ``dashpot init`` refused, or whose Project configuration could not be written."""


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
    config_path = root / PROJECT_CONFIG_PATH
    if config_path.is_file():
        raise InitError(f"already configured: {config_path}")
    reference = github_repo_from_remote(root, adapter)
    if markdown_path is not None:
        try:
            issue_source: IssueSourceConfig = LocalMarkdownIssueSourceConfig(
                kind="markdown", path=markdown_path
            )
        except ValidationError as exc:
            raise InitError(f"--markdown {describe_validation_error(exc)}") from exc
        repository_id = f"repository:{uuid.uuid4()}"
        display_label = root.name
    elif reference is not None:
        repository_id, observed_reference = observe_github_repository_identity(
            root, reference, timeout, runner
        )
        display_label = observed_reference.rpartition("/")[2]
        issue_source = GitHubIssueSourceConfig(kind="github")
    else:
        raise InitError(
            f"{root} has no GitHub origin remote; pass --markdown PATH to "
            f"declare a Local Issue Markdown source"
        )
    try:
        # Validated under the file's own keys, so a refusal names the field
        # as the configuration spells it.
        config = ProjectConfig.model_validate(
            {
                "projectId": f"project:{uuid.uuid4()}",
                "displayLabel": display_label,
                "repositoryId": repository_id,
                "issueSource": issue_source,
            }
        )
    except ValidationError as exc:
        raise InitError(
            f"cannot declare this Project: {describe_validation_error(exc)}"
        ) from exc
    # Only the fields init chose are written: a default the loader supplies,
    # such as the retired ``reconciliationSeconds``, stays out of the file.
    text = config.model_dump_json(by_alias=True, exclude_unset=True, indent=2)
    try:
        config_path.parent.mkdir(exist_ok=True)
        config_path.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        # A write that failed part-way must not leave a file a second run
        # would take for a configuration; none was there before it.
        with suppress(OSError):
            config_path.unlink(missing_ok=True)
        raise InitError(
            f"cannot write Project configuration {config_path}: {exc}"
        ) from exc
    return [f"created {config_path}"]
