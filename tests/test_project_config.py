from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dashpot.collect import (
    build_issue_source,
    build_pull_request_source,
    create_project_collector,
)
from dashpot.github_issues import GitHubIssuesSource
from dashpot.github_pull_requests import GitHubPullRequestsSource
from dashpot.issue_resolution import configured_issue_source
from dashpot.local_markdown_issues import LocalMarkdownIssuesSource
from dashpot.model import ResolvedProject
from dashpot.project_config import (
    PROJECT_CONFIG_NAME,
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    load_project_config,
    parse_project_config,
)
from dashpot.pull_request_sources import UnconfiguredPullRequestSource
from factories import completed, fake_git, init_repository, write_project_config

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
    assert config.issue_source == GitHubIssueSourceConfig(kind="github")


def test_loads_local_markdown_project_configuration(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "markdown", "path": "issues"})

    config = load_project_config(tmp_path)

    assert config.issue_source == LocalMarkdownIssueSourceConfig(
        kind="markdown", path="issues"
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ({"kind": "markdown", "path": "../outside"}, "repository-relative"),
        ({"kind": "github", "repositoryId": "nested"}, "unexpected fields"),
        ({"kind": "unknown"}, "must be 'github' or 'markdown'"),
        ({"kind": "markdown"}, "issueSource is missing fields: path"),
        ({"kind": "markdown", "path": 3}, "issueSource.path must be a string"),
        ({"kind": "markdown", "path": " "}, "issueSource.path must be a non-empty"),
    ],
)
def test_rejects_invalid_issue_source_configuration(
    tmp_path: Path, source: dict[str, Any], message: str
) -> None:
    write_config(tmp_path, source)

    with pytest.raises(RuntimeError, match=message):
        load_project_config(tmp_path)


def test_a_missing_project_configuration_names_its_path(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Project configuration not found"):
        load_project_config(tmp_path)


def test_an_unreadable_project_configuration_names_its_path(tmp_path: Path) -> None:
    # A directory where the file belongs raises OSError on read, not absence.
    (tmp_path / PROJECT_CONFIG_NAME).mkdir(parents=True)

    with pytest.raises(RuntimeError, match="cannot read Project configuration"):
        load_project_config(tmp_path)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{not json", "cannot read Project configuration"),
        ('["not", "an", "object"]', "must contain a JSON object"),
        ('{"projectId": "p"}', "is missing fields"),
        (
            '{"projectId": " ", "displayLabel": "d", "repositoryId": "r",'
            ' "issueSource": {"kind": "github"}}',
            "projectId must be a non-empty string",
        ),
        (
            '{"projectId": "p", "displayLabel": "d", "repositoryId": "r",'
            ' "issueSource": "github"}',
            "issueSource must be an object",
        ),
    ],
)
def test_rejects_malformed_project_configuration_text(
    tmp_path: Path, text: str, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        parse_project_config(text, tmp_path / PROJECT_CONFIG_NAME)


def test_configuration_strings_are_stripped_and_the_model_is_frozen(
    tmp_path: Path,
) -> None:
    write_project_config(
        tmp_path,
        project_id=f" {PROJECT_ID} ",
        display_label=" Dashpot ",
        repository_id="R_dashpot",
        issue_source={"kind": "markdown", "path": " issues "},
    )

    config = load_project_config(tmp_path)

    assert config.project_id == PROJECT_ID
    assert config.display_label == "Dashpot"
    assert config.issue_source == LocalMarkdownIssueSourceConfig(
        kind="markdown", path="issues"
    )
    with pytest.raises(ValidationError):
        config.display_label = "Renamed"  # ty: ignore[invalid-assignment]


def test_project_configuration_forbids_coercion_and_unknown_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / PROJECT_CONFIG_NAME
    document = {
        "projectId": PROJECT_ID,
        "displayLabel": 1,
        "repositoryId": "R_dashpot",
        "issueSource": {"kind": "github"},
    }

    with pytest.raises(RuntimeError, match="displayLabel must be a string"):
        parse_project_config(json.dumps(document), path)

    document["displayLabel"] = "Dashpot"
    document["extra"] = True
    with pytest.raises(RuntimeError, match="has unexpected fields: extra"):
        parse_project_config(json.dumps(document), path)


def test_project_collector_rejects_changed_configuration(tmp_path: Path) -> None:
    # Configuration edited between Project resolution and collector creation
    # must be re-resolved, not silently mixed with the stale resolution.
    write_config(tmp_path, {"kind": "markdown", "path": "issues"})
    git = fake_git(completed(f"{tmp_path}\n"))
    renamed = ResolvedProject(
        PROJECT_ID,
        "Renamed",
        "R_dashpot",
        ("test",),
        (str(tmp_path),),
        str(tmp_path),
    )

    with pytest.raises(RuntimeError, match="configuration changed after resolving"):
        create_project_collector(renamed, git=git)


def test_project_collector_builds_local_markdown_source(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "markdown", "path": "issues"})
    git = fake_git(completed(f"{tmp_path}\n"))

    collector = create_project_collector(project(tmp_path), git=git)

    assert isinstance(collector.source, LocalMarkdownIssuesSource)
    assert collector.source.project_id == PROJECT_ID
    assert collector.source.issues_path == Path("issues")
    assert isinstance(collector.pull_request_source, UnconfiguredPullRequestSource)
    pull_requests = collector.pull_request_source.refresh()
    assert pull_requests.status == "unavailable"
    assert pull_requests.diagnostics[0].code == "pull-requests-not-configured"


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
    assert isinstance(collector.pull_request_source, GitHubPullRequestsSource)
    assert collector.pull_request_source.repository_id == "R_dashpot"


def test_github_source_requires_github_repository_anchor(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "github"})
    git = fake_git(
        completed(f"{tmp_path}\n"),
        completed(stderr="error: No such remote 'origin'", returncode=2),
    )

    with pytest.raises(RuntimeError, match="GitHub origin remote"):
        create_project_collector(project(tmp_path), git=git)


def test_build_issue_source_builds_the_configured_github_source(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, {"kind": "github"})
    git = fake_git(completed("https://github.com/ned2/dashpot.git\n"))

    source = build_issue_source(
        tmp_path, load_project_config(tmp_path), timeout=7, git=git
    )

    assert isinstance(source, GitHubIssuesSource)
    assert source.project_id == PROJECT_ID
    assert source.repository_id == "R_dashpot"
    assert source.timeout == 7


def test_build_issue_source_requires_github_repository_anchor(tmp_path: Path) -> None:
    write_config(tmp_path, {"kind": "github"})
    git = fake_git(completed(stderr="error: No such remote 'origin'", returncode=2))

    with pytest.raises(RuntimeError, match="GitHub origin remote"):
        build_issue_source(tmp_path, load_project_config(tmp_path), timeout=7, git=git)


def test_build_pull_request_source_follows_the_configured_issue_source(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, {"kind": "github"})
    config = load_project_config(tmp_path)

    source = build_pull_request_source(tmp_path, config, timeout=7)

    assert isinstance(source, GitHubPullRequestsSource)
    assert source.repository_id == "R_dashpot"
    assert source.gateway.timeout == 7

    write_config(tmp_path, {"kind": "markdown", "path": "issues"})
    local_source = build_pull_request_source(
        tmp_path, load_project_config(tmp_path), timeout=7
    )
    assert isinstance(local_source, UnconfiguredPullRequestSource)


def test_every_entry_point_builds_the_same_issue_source(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path / "repo", origin="https://github.com/ned2/dashpot.git"
    )
    write_config(root, {"kind": "github"})

    direct = build_issue_source(root, load_project_config(root), timeout=10)
    resolved = configured_issue_source(root)
    collector = create_project_collector(project(root))

    for source in (direct, resolved, collector.source):
        assert isinstance(source, GitHubIssuesSource)
        assert source.project_id == PROJECT_ID
        assert source.repository_id == "R_dashpot"
        assert source.timeout == 10
