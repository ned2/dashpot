from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dashpot.issue_profile import conform_issue
from dashpot.issue_resolution import describe_issue, resolve_issue, show_issue
from helpers import make_issue
from test_work import issue_document


def repository(root: Path, *, issues_path: str = "issues") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".dashpot").mkdir()
    (root / ".dashpot" / "config.json").write_text(
        json.dumps(
            {
                "projectId": "project:test",
                "displayLabel": "Test",
                "repositoryId": "repository:test",
                "issueSource": {"kind": "markdown", "path": issues_path},
            }
        )
    )
    issues = root / "issues"
    issues.mkdir()
    (issues / "worktree-protocol.md").write_text(
        issue_document(
            issue_id="I_35",
            number=35,
            reference="worktree-protocol",
            title="Worktree protocol",
        )
    )
    (issues / "other.md").write_text(
        issue_document(issue_id="I_36", number=36, reference="other", title="Other")
    )
    return root


@pytest.mark.parametrize("hint", ["35", "#35", "worktree-protocol"])
def test_number_prefixed_number_and_slug_resolve_to_one_issue(
    tmp_path: Path, hint: str
) -> None:
    root = repository(tmp_path / "repo")

    issue = resolve_issue(root, hint)

    assert issue.id == "I_35"
    assert issue.reference == "worktree-protocol"


def test_full_github_reference_matches_nothing_in_a_markdown_project(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")

    with pytest.raises(RuntimeError, match="did not match an Issue"):
        resolve_issue(root, "ned2/sim#35")


def test_a_miss_is_an_actionable_error(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    with pytest.raises(RuntimeError, match="'99' did not match an Issue"):
        resolve_issue(root, "99")


def test_an_unavailable_source_refuses_resolution(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", issues_path="missing")

    with pytest.raises(RuntimeError, match="Issue Source is unavailable"):
        resolve_issue(root, "35")


def test_show_resolves_from_a_subdirectory_and_returns_the_profile(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)

    issue = show_issue(nested, "35")

    assert conform_issue(issue.model_dump(mode="json", by_alias=True)) == issue
    assert issue.location.model_dump(by_alias=True) == {
        "kind": "markdown",
        "path": "issues/worktree-protocol.md",
        "line": 24,
    }


def test_describe_issue_names_reference_title_state_and_location(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")

    lines = describe_issue(resolve_issue(root, "35"))

    assert lines[0] == "worktree-protocol: Worktree protocol"
    assert "number: #35" in lines
    assert "state: open" in lines
    assert "location: issues/worktree-protocol.md:24" in lines
    assert "id: I_35" in lines


def test_describe_issue_renders_a_github_location_as_its_url() -> None:
    issue = make_issue(
        id="I_x",
        number=35,
        reference="ned2/dashpot#35",
        title="T",
        state="closed",
        stateReason="completed",
        location={
            "kind": "github",
            "url": "https://github.com/ned2/dashpot/issues/35",
        },
    )

    lines = describe_issue(issue)

    assert "state: closed (completed)" in lines
    assert "location: https://github.com/ned2/dashpot/issues/35" in lines
