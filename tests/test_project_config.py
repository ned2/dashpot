from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dashpot.collect import create_project_collector
from dashpot.github_issues import GitHubIssuesSource
from dashpot.local_markdown_issues import LocalMarkdownIssuesSource
from dashpot.model import ResolvedProject
from dashpot.project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    load_project_config,
)
from factories import completed, fake_git, write_project_config

PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"


def write_config(root: Path, issue_source: dict[str, Any]) -> None:
    write_project_config(
        root,
        project_id=PROJECT_ID,
        display_label="Dashpot",
        repository_id="R_dashpot",
        issue_source=issue_source,
    )


def project(root: Path) -> ResolvedProject:
    return ResolvedProject(
        PROJECT_ID,
        "Dashpot",
        "R_dashpot",
        ("test",),
        (str(root),),
        str(root),
    )


def test_loads_github_project_configuration(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "github"})

    config = load_project_config(tmp_path)

    assert config.project_id == PROJECT_ID
    assert config.display_label == "Dashpot"
    assert config.repository_id == "R_dashpot"
    assert config.issue_source == GitHubIssueSourceConfig("github")


def test_loads_local_markdown_project_configuration(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "markdown", "path": "issues"})

    config = load_project_config(tmp_path)

    assert config.issue_source == LocalMarkdownIssueSourceConfig("markdown", "issues")


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ({"kind": "markdown", "path": "../outside"}, "repository-relative"),
        ({"kind": "github", "repositoryId": "nested"}, "unexpected fields"),
        ({"kind": "unknown"}, "must be 'github' or 'markdown'"),
    ],
)
def test_rejects_invalid_issue_source_configuration(
    tmp_path: Path, source: dict[str, Any], message: str
) -> None:
    write_config(tmp_path, source)

    with pytest.raises(RuntimeError, match=message):
        load_project_config(tmp_path)


def test_project_collector_builds_local_markdown_source(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "markdown", "path": "issues"})
    git = fake_git(completed(f"{tmp_path}\n"))

    collector = create_project_collector(project(tmp_path), git=git)

    assert isinstance(collector.source, LocalMarkdownIssuesSource)
    assert collector.source.project_id == PROJECT_ID
    assert collector.source.issues_path == Path("issues")


def test_project_collector_builds_github_source_for_github_anchor(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, {"kind": "github"})
    git = fake_git(
        completed(f"{tmp_path}\n"),
        completed("https://github.com/ned2/dashpot.git\n"),
    )

    collector = create_project_collector(project(tmp_path), git=git)

    assert isinstance(collector.source, GitHubIssuesSource)
    assert collector.source.project_id == PROJECT_ID
    assert collector.source.repository_id == "R_dashpot"


def test_github_source_requires_github_repository_anchor(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "github"})
    git = fake_git(
        completed(f"{tmp_path}\n"),
        completed(stderr="error: No such remote 'origin'", returncode=2),
    )

    with pytest.raises(RuntimeError, match="GitHub origin remote"):
        create_project_collector(project(tmp_path), git=git)
