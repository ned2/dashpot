from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from dashpot.core.commands import CommandResult, CommandRunner
from dashpot.github.github import GitHubRequestError
from dashpot.project.init import InitError, initialize_project
from factories import init_repository


def gh_runner(payload: dict[str, Any]) -> tuple[list[list[str]], CommandRunner]:
    calls: list[list[str]] = []

    def runner(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        calls.append(list(args))
        return CommandResult(list(args), 0, json.dumps(payload), "")

    return calls, runner


def load_config(root: Path) -> dict[str, Any]:
    return json.loads((root / ".dashpot" / "config.json").read_text())


def test_github_origin_initializes_with_resolved_identity(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path / "repo", origin="https://github.com/ned2/dashpot.git"
    )
    calls, runner = gh_runner({"node_id": "R_dashpot", "full_name": "ned2/dashpot"})

    messages = initialize_project(root, runner=runner)

    config = load_config(root)
    assert config["repositoryId"] == "R_dashpot"
    assert config["displayLabel"] == "dashpot"
    assert config["issueSource"] == {"kind": "github"}
    assert config["projectId"].startswith("project:")
    assert ["gh", "api", "repos/ned2/dashpot"] in calls
    assert messages[0] == f"created {root / '.dashpot' / 'config.json'}"


def test_markdown_initializes_without_github(git_repository: Path) -> None:
    root = git_repository

    initialize_project(root, markdown_path="issues")

    config = load_config(root)
    assert config["repositoryId"].startswith("repository:")
    assert config["displayLabel"] == "repo"
    assert config["issueSource"] == {"kind": "markdown", "path": "issues"}


def test_markdown_takes_precedence_over_github_origin(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path / "repo", origin="https://github.com/ned2/dashpot.git"
    )
    calls, runner = gh_runner({})

    initialize_project(root, markdown_path="issues", runner=runner)

    assert load_config(root)["issueSource"]["kind"] == "markdown"
    assert not [call for call in calls if call[0] == "gh"]


@pytest.mark.parametrize("path", ["/absolute", "../outside"])
def test_markdown_path_must_be_repository_relative(
    git_repository: Path, path: str
) -> None:
    root = git_repository

    with pytest.raises(InitError, match="repository-relative"):
        initialize_project(root, markdown_path=path)


def test_init_requires_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(InitError, match="inside a Git repository"):
        initialize_project(tmp_path)


def test_init_refuses_to_overwrite_existing_configuration(
    git_repository: Path,
) -> None:
    root = git_repository
    initialize_project(root, markdown_path="issues")

    with pytest.raises(InitError, match="already configured"):
        initialize_project(root, markdown_path="issues")


def test_no_origin_without_markdown_is_an_actionable_error(
    git_repository: Path,
) -> None:
    root = git_repository

    with pytest.raises(InitError, match="--markdown"):
        initialize_project(root)

    assert not (root / ".dashpot").exists()


def test_gh_failure_leaves_no_partial_configuration(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path / "repo", origin="https://github.com/ned2/dashpot.git"
    )

    def runner(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        return CommandResult(list(args), 1, "", "gh: Not Found")

    with pytest.raises(GitHubRequestError, match="cannot resolve GitHub repository"):
        initialize_project(root, runner=runner)

    assert not (root / ".dashpot").exists()


def test_gives_no_ignore_advice_since_the_state_directory_ignores_itself(
    git_repository: Path,
) -> None:
    root = git_repository

    messages = initialize_project(root, markdown_path="issues")

    assert messages == [f"created {root / '.dashpot' / 'config.json'}"]
    assert not (root / ".gitignore").exists()
    assert not (root / ".dashpot" / "state").exists()


def test_init_runs_at_the_worktree_root_from_a_subdirectory(
    git_repository: Path,
) -> None:
    root = git_repository
    nested = root / "src" / "package"
    nested.mkdir(parents=True)

    initialize_project(nested, markdown_path="issues")

    assert (root / ".dashpot" / "config.json").is_file()
