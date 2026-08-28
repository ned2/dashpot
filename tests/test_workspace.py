from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from dashpot.model import RepositoryAnchor, Workspace
from dashpot.workspace import load_workspaces, resolve_workspace_projects

PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"


def write_project(
    root: Path,
    *,
    project_id: str = PROJECT_ID,
    display_label: str = "Dashpot",
    repository_id: str = "repository:dashpot",
    source: dict | None = None,
) -> None:
    (root / ".dashpot").mkdir(parents=True, exist_ok=True)
    (root / ".dashpot" / "config.json").write_text(
        json.dumps(
            {
                "projectId": project_id,
                "displayLabel": display_label,
                "repositoryId": repository_id,
                "issueSource": source or {"kind": "markdown", "path": "issues"},
            }
        )
    )


def root_observer(path: Path) -> Path:
    return path.resolve()


def workspace(name: str, *roots: Path) -> Workspace:
    return Workspace(
        name,
        tuple(RepositoryAnchor(str(root.resolve())) for root in roots),
    )


def test_workspace_config_explicitly_lists_repository_anchors(tmp_path: Path) -> None:
    config = tmp_path / "workspaces.json"
    config.write_text(
        json.dumps(
            {
                "workspaces": [
                    {
                        "name": "personal",
                        "anchors": ["../one", "/absolute/two"],
                    }
                ]
            }
        )
    )

    result = load_workspaces(config)

    assert result == [
        Workspace(
            "personal",
            (
                RepositoryAnchor(str((tmp_path / "../one").resolve())),
                RepositoryAnchor("/absolute/two"),
            ),
        )
    ]


def test_workspace_config_rejects_legacy_discovery_root(tmp_path: Path) -> None:
    config = tmp_path / "workspaces.json"
    config.write_text(
        json.dumps({"workspaces": [{"name": "old", "root": "/projects"}]})
    )

    with pytest.raises(RuntimeError, match="missing fields: anchors"):
        load_workspaces(config)


def test_independent_clones_resolve_to_one_project_with_one_primary_anchor(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first-clone"
    second = tmp_path / "second-clone"
    write_project(first)
    write_project(second)

    result = resolve_workspace_projects(
        [workspace("personal", first, second)],
        root_observer=root_observer,
    )

    assert result.diagnostics == []
    assert len(result.projects) == 1
    project = result.projects[0]
    assert project.project_id == PROJECT_ID
    assert project.display_label == "Dashpot"
    assert project.repository_id == "repository:dashpot"
    assert project.anchors == (str(first.resolve()), str(second.resolve()))
    assert project.primary_anchor == str(first.resolve())


def test_same_project_can_belong_to_two_workspaces_and_each_anchor_is_validated(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dashpot"
    write_project(root)
    observed: list[Path] = []

    def observe(path: Path) -> Path:
        observed.append(path)
        return root_observer(path)

    result = resolve_workspace_projects(
        [workspace("personal", root), workspace("client", root)],
        root_observer=observe,
    )

    assert observed == [root.resolve(), root.resolve()]
    assert result.projects[0].workspaces == ("personal", "client")
    assert result.projects[0].anchors == (str(root.resolve()),)


def test_display_label_drift_does_not_split_project_identity(
    tmp_path: Path,
) -> None:
    primary = tmp_path / "primary"
    stale_clone = tmp_path / "stale-clone"
    write_project(primary, display_label="Current label")
    write_project(stale_clone, display_label="Old label")

    result = resolve_workspace_projects(
        [workspace("personal", primary, stale_clone)],
        root_observer=root_observer,
    )

    assert result.diagnostics == []
    assert len(result.projects) == 1
    assert result.projects[0].display_label == "Current label"


def test_moving_checkout_changes_only_anchor_location(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    write_project(before)
    write_project(after)

    old = resolve_workspace_projects(
        [workspace("personal", before)], root_observer=root_observer
    ).projects[0]
    moved = resolve_workspace_projects(
        [workspace("personal", after)], root_observer=root_observer
    ).projects[0]

    assert old.project_id == moved.project_id
    assert old.repository_id == moved.repository_id
    assert old.display_label == moved.display_label
    assert old.primary_anchor != moved.primary_anchor


def test_conflicting_repository_identities_never_form_a_project(
    tmp_path: Path,
) -> None:
    original = tmp_path / "original"
    copied = tmp_path / "copied"
    write_project(original, repository_id="repository:original")
    write_project(copied, repository_id="repository:copy")

    result = resolve_workspace_projects(
        [workspace("personal", original, copied)],
        root_observer=root_observer,
    )

    assert result.projects == []
    assert result.diagnostics[0].code == "project-repository-conflict"
    assert PROJECT_ID in result.diagnostics[0].message
    assert "repository:original" in result.diagnostics[0].message
    assert "repository:copy" in result.diagnostics[0].message


def test_conflicting_issue_sources_never_form_a_project(tmp_path: Path) -> None:
    github_clone = tmp_path / "github-source"
    markdown_clone = tmp_path / "markdown-source"
    write_project(
        github_clone,
        repository_id="R_dashpot",
        source={"kind": "github"},
    )
    write_project(
        markdown_clone,
        repository_id="R_dashpot",
        source={"kind": "markdown", "path": "issues"},
    )

    with mock.patch(
        "dashpot.workspace.github_repo_from_remote", return_value="ned2/dashpot"
    ):
        result = resolve_workspace_projects(
            [workspace("personal", github_clone, markdown_clone)],
            root_observer=root_observer,
            github_identity_observer=lambda _root, _reference, _timeout: (
                "R_dashpot",
                "ned2/dashpot",
            ),
        )

    assert result.projects == []
    assert result.diagnostics[0].code == "project-source-conflict"
    assert PROJECT_ID in result.diagnostics[0].message


def test_github_fork_retaining_project_identity_is_diagnosed(
    tmp_path: Path,
) -> None:
    fork = tmp_path / "fork"
    write_project(
        fork,
        repository_id="R_original",
        source={"kind": "github"},
    )

    with mock.patch(
        "dashpot.workspace.github_repo_from_remote", return_value="someone/fork"
    ):
        result = resolve_workspace_projects(
            [workspace("personal", fork)],
            root_observer=root_observer,
            github_identity_observer=lambda _root, _reference, _timeout: (
                "R_fork",
                "someone/fork",
            ),
        )

    assert result.projects == []
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "repository-identity-conflict"
    assert PROJECT_ID in diagnostic.message
    assert "R_original" in diagnostic.message
    assert "R_fork" in diagnostic.message
