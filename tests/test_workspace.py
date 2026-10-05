from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dashpot.project.workspace import (
    RepositoryAnchor,
    Workspace,
    WorkspaceConfigError,
    WorkspaceInventory,
    WorkspaceScopeError,
    default_workspace_config,
    load_workspaces,
    resolve_workspace_projects,
)
from factories import completed, fake_git, write_project_config

PROJECT_ID = "project:01947e42-3f67-7c38-a41c-218df18a169b"


def write_project(
    root: Path,
    *,
    project_id: str = PROJECT_ID,
    display_label: str = "Dashpot",
    repository_id: str = "repository:dashpot",
    source: dict[str, Any] | None = None,
) -> None:
    write_project_config(
        root,
        project_id=project_id,
        display_label=display_label,
        repository_id=repository_id,
        issue_source=source,
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

    assert result == WorkspaceInventory(
        (
            Workspace(
                "personal",
                (
                    RepositoryAnchor(str((tmp_path / "../one").resolve())),
                    RepositoryAnchor("/absolute/two"),
                ),
            ),
        )
    )


def test_workspace_config_rejects_legacy_discovery_root(tmp_path: Path) -> None:
    config = tmp_path / "workspaces.json"
    config.write_text(
        json.dumps({"workspaces": [{"name": "old", "root": "/projects"}]})
    )

    with pytest.raises(
        WorkspaceConfigError, match="workspace entry 0 is missing fields: anchors"
    ):
        load_workspaces(config)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("[]", "must contain a JSON object"),
        ('{"workspaces": {}}', "workspaces must be"),
        ('{"workspaces": ["x"]}', "workspace entry 0 must be an object"),
        (
            '{"workspaces": [{"name": " ", "anchors": ["a"]}]}',
            "name must be a non-empty",
        ),
        ('{"workspaces": [{"name": "n", "anchors": []}]}', "anchors must not be empty"),
        (
            '{"workspaces": [{"name": "n", "anchors": ["a", 3]}]}',
            "workspace entry 0 anchor 1 must be a string",
        ),
        (
            '{"workspaces": [{"name": "n", "anchors": ["a", " "]}]}',
            "workspace entry 0 anchor 1 must be a non-empty string",
        ),
    ],
)
def test_malformed_workspace_config_is_refused_by_entry(
    tmp_path: Path, document: str, message: str
) -> None:
    config = tmp_path / "workspaces.json"
    config.write_text(document)

    with pytest.raises(WorkspaceConfigError, match=message):
        load_workspaces(config)


def test_a_workspace_config_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "workspaces.json"
    config.write_bytes(b'{"workspaces": [{"name": "caf\xe9", "anchors": ["/a"]}]}')

    with pytest.raises(WorkspaceConfigError, match="cannot read workspace config"):
        load_workspaces(config)


def test_unknown_workspace_config_fields_are_ignored_with_a_diagnostic(
    tmp_path: Path,
) -> None:
    # A field written by a newer Dashpot must not stop this one starting.
    config = tmp_path / "workspaces.json"
    config.write_text(
        json.dumps(
            {
                "version": 2,
                "workspaces": [{"name": " personal ", "anchors": ["one"], "color": 1}],
            }
        )
    )

    result = load_workspaces(config)

    assert result.workspaces == (
        Workspace("personal", (RepositoryAnchor(str((tmp_path / "one").resolve())),)),
    )
    (diagnostic,) = result.diagnostics
    assert diagnostic.code == "workspace-config-unknown-field"
    assert "version, workspaces[0].color" in diagnostic.message


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

    result = resolve_workspace_projects(
        [workspace("personal", github_clone, markdown_clone)],
        root_observer=root_observer,
        github_identity_observer=lambda _root, _reference, _timeout: (
            "R_dashpot",
            "ned2/dashpot",
        ),
        git=fake_git(completed("https://github.com/ned2/dashpot.git\n")),
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

    result = resolve_workspace_projects(
        [workspace("personal", fork)],
        root_observer=root_observer,
        github_identity_observer=lambda _root, _reference, _timeout: (
            "R_fork",
            "someone/fork",
        ),
        git=fake_git(completed("https://github.com/someone/fork.git\n")),
    )

    assert result.projects == []
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "repository-identity-conflict"
    assert PROJECT_ID in diagnostic.message
    assert "R_original" in diagnostic.message
    assert "R_fork" in diagnostic.message


def test_anchors_resolving_to_two_projects_are_refused_before_observation(
    tmp_path: Path,
) -> None:
    dashpot = tmp_path / "dashpot"
    other = tmp_path / "other"
    write_project(dashpot)
    write_project(
        other,
        project_id="project:0195aaaa-1111-7c38-a41c-218df18a169b",
        display_label="Other",
        repository_id="repository:other",
    )

    with pytest.raises(WorkspaceScopeError) as raised:
        resolve_workspace_projects(
            [workspace("personal", dashpot), workspace("client", other)],
            root_observer=root_observer,
        )

    message = str(raised.value)
    assert "one Project per run" in message
    assert "2 Projects" in message
    assert f"Dashpot ({PROJECT_ID}) at {dashpot.resolve()}" in message
    assert (
        f"Other (project:0195aaaa-1111-7c38-a41c-218df18a169b) at {other.resolve()}"
        in message
    )
    assert [project.display_label for project in raised.value.projects] == [
        "Dashpot",
        "Other",
    ]


def test_the_workspace_inventory_follows_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert (
        default_workspace_config() == tmp_path / "xdg" / "dashpot" / "workspaces.json"
    )


@pytest.mark.parametrize("value", ["config", "./config", ""])
def test_a_relative_xdg_config_home_is_ignored_for_the_workspace_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    # The XDG specification makes a relative value invalid: honouring it
    # would give each process the inventory under its own working directory.
    monkeypatch.setenv("XDG_CONFIG_HOME", value)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    assert default_workspace_config() == (
        tmp_path / "home" / ".config" / "dashpot" / "workspaces.json"
    )


def test_a_symlink_loop_is_only_its_own_anchors_diagnostic(tmp_path: Path) -> None:
    root = tmp_path / "dashpot"
    write_project(root)
    loop = tmp_path / "loop"
    loop.symlink_to(loop)

    named = resolve_workspace_projects(
        [workspace("personal", loop, root)], root_observer=root_observer
    )
    # ``resolve`` leaves a loop the root observer reports unresolved, so
    # reading the Project configuration through it is what fails.
    observed = resolve_workspace_projects(
        [workspace("personal", root)], root_observer=lambda path: loop
    )

    assert [project.anchors for project in named.projects] == [(str(root.resolve()),)]
    assert [(item.source, item.code) for item in named.diagnostics] == [
        (f"anchor:{loop}", "repository-anchor")
    ]
    assert observed.projects == []
    (diagnostic,) = observed.diagnostics
    assert (diagnostic.source, diagnostic.code) == (
        f"anchor:{root.resolve()}",
        "repository-anchor",
    )
    assert diagnostic.message.startswith(
        f"cannot read Project configuration {loop / '.dashpot' / 'config.json'}: "
    )


def test_a_project_configuration_nested_too_deeply_is_its_anchors_diagnostic(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dashpot"
    write_project(root)
    config = root / ".dashpot" / "config.json"
    config.write_text("[" * 200_000)

    result = resolve_workspace_projects(
        [workspace("personal", root)], root_observer=root_observer
    )

    assert result.projects == []
    (diagnostic,) = result.diagnostics
    assert (diagnostic.source, diagnostic.code) == (
        f"anchor:{root.resolve()}",
        "repository-anchor",
    )
    # ``json`` raises ``RecursionError``, whose text differs between 3.13
    # and 3.14 but names what it was decoding in both.
    assert diagnostic.message.startswith(
        f"cannot read Project configuration {config.resolve()}: "
    )
    assert "while decoding a JSON array" in diagnostic.message
