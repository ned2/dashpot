from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

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


PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"


def write_config(root: Path, issue_source: dict) -> None:
    (root / ".dashpot").mkdir(exist_ok=True)
    (root / ".dashpot" / "config.json").write_text(
        json.dumps(
            {
                "projectId": PROJECT_ID,
                "displayLabel": "Dashpot",
                "repositoryId": "R_dashpot",
                "issueSource": issue_source,
            }
        )
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

    assert config.issue_source == LocalMarkdownIssueSourceConfig(
        "markdown", "issues"
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ({"kind": "markdown", "path": "../outside"}, "repository-relative"),
        ({"kind": "github", "repositoryId": "nested"}, "unexpected fields"),
        ({"kind": "unknown"}, "must be 'github' or 'markdown'"),
    ],
)
def test_rejects_invalid_issue_source_configuration(
    tmp_path: Path, source: dict, message: str
) -> None:
    write_config(tmp_path, source)

    with pytest.raises(RuntimeError, match=message):
        load_project_config(tmp_path)


def test_project_collector_builds_local_markdown_source(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "markdown", "path": "issues"})

    with mock.patch(
        "dashpot.collect.worktree_root", return_value=tmp_path
    ):
        collector = create_project_collector(project(tmp_path))

    assert isinstance(collector.source, LocalMarkdownIssuesSource)
    assert collector.source.project_id == PROJECT_ID
    assert collector.source.issues_path == Path("issues")


def test_project_collector_builds_github_source_for_github_anchor(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, {"kind": "github"})

    with mock.patch(
        "dashpot.collect.worktree_root", return_value=tmp_path
    ), mock.patch(
        "dashpot.collect.github_repo_from_remote", return_value="ned2/dashpot"
    ):
        collector = create_project_collector(project(tmp_path))

    assert isinstance(collector.source, GitHubIssuesSource)
    assert collector.source.project_id == PROJECT_ID
    assert collector.source.repository_id == "R_dashpot"


def test_github_source_requires_github_repository_anchor(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "github"})

    with mock.patch(
        "dashpot.collect.worktree_root", return_value=tmp_path
    ), mock.patch("dashpot.collect.github_repo_from_remote", return_value=None):
        with pytest.raises(RuntimeError, match="GitHub origin remote"):
            create_project_collector(project(tmp_path))
