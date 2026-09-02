from __future__ import annotations

from pathlib import Path

import pytest

from dashpot.issue_profile import conform_issue
from dashpot.issue_resolution import describe_issue, resolve_issue, show_issue
from factories import WORKTREE_PROTOCOL_ISSUES, dashpot_project
from helpers import make_issue


def repository(root: Path, *, issues_path: str = "issues") -> Path:
    return dashpot_project(
        root, issues=WORKTREE_PROTOCOL_ISSUES, issues_path=issues_path
    )


@pytest.mark.parametrize("hint", ["35", "#35", "worktree-protocol", " 35 ", "\t#35\n"])
def test_number_prefixed_number_slug_and_whitespace_resolve_to_one_issue(
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


def test_a_pasted_github_url_matches_nothing_in_a_markdown_project(
    tmp_path: Path,
) -> None:
    # The URL parses to the repository-qualified Reference it names, so it
    # cannot fall back to matching a Local Issue by bare number.
    root = repository(tmp_path / "repo")

    with pytest.raises(RuntimeError, match="did not match an Issue"):
        resolve_issue(root, "https://github.com/ned2/dashpot/issues/35")


def test_a_slug_resolves_cheaply_past_a_broken_sibling_document(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    (root / "issues" / "broken.md").write_text("not a Local Issue document\n")

    issue = resolve_issue(root, "worktree-protocol")

    assert issue.id == "I_35"
    with pytest.raises(RuntimeError, match="Issue Source is unavailable"):
        resolve_issue(root, "35")


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
