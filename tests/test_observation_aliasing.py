"""Aliasing safety net for the frozen observation values (ADR 0013 step 7).

Isolation is proven in both directions before any deepcopy guard goes:
mutating the caller's input collections after publication must not change
what the store or a source reports, and the published value's own
collections must reject mutation outright.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from typing_extensions import override

import factories
from dashpot.issue_profile import IssueProfile
from dashpot.issue_sources import IssueSource, IssueSourceRefreshError
from dashpot.model import IssueActivity, WorkspaceSnapshot
from dashpot.observation_store import WorkspaceObservationStore
from factories import agent_run, project, workspace
from helpers import make_issue, required, snapshot_of


def issue(issue_id: str, title: str) -> IssueProfile:
    return make_issue(
        id=issue_id,
        number=1,
        state="open",
        title=title,
        labels=[],
        assignees=[],
        author=None,
        milestone=None,
        issueType=None,
    )


class _ScriptedSource(IssueSource):
    """An Issue Source that returns the collections the test hands it."""

    def __init__(
        self,
        issues: list[IssueProfile],
        label_colors: dict[str, str],
        issue_activity: dict[str, IssueActivity],
    ) -> None:
        super().__init__(clock=lambda: factories.NOW)
        self._issues = issues
        self._label_colors = label_colors
        self._issue_activity = issue_activity
        self.fail = False

    @property
    @override
    def name(self) -> str:
        return "scripted"

    @override
    def _collect(self) -> list[IssueProfile]:
        if self.fail:
            raise IssueSourceRefreshError("scripted-down", "scripted failure")
        return self._issues

    @override
    def _collect_label_colors(self) -> dict[str, str]:
        return self._label_colors

    @override
    def _collect_issue_activity(self) -> dict[str, IssueActivity]:
        return self._issue_activity


# --- Direction one: the caller's input, mutated after publication ------------


def test_store_is_isolated_from_the_callers_input_collections() -> None:
    bound_run = agent_run("codex:one", "project:one", issue_id="I_one")
    projects_input = [project("project:one", issue("I_one", "First"))]
    runs_input = [bound_run]
    run_ids_input = ["codex:one"]
    issue_runs_input = {"I_one": run_ids_input}
    snapshot = WorkspaceSnapshot(
        collected_at=factories.NOW,
        elapsed_ms=9,
        projects=projects_input,
        agent_runs=runs_input,
        issue_runs=issue_runs_input,
        diagnostics=[],
    )
    store = WorkspaceObservationStore(snapshot)

    projects_input.append(project("project:two", issue("I_two", "Second")))
    runs_input.append(agent_run("codex:two", "project:one", issue_id="I_one"))
    run_ids_input.append("codex:two")
    issue_runs_input["I_two"] = ["codex:rogue"]

    checkpoint = store.checkpoint()
    assert [entry.project_id for entry in checkpoint.projects] == ["project:one"]
    assert [entry.id for entry in checkpoint.agent_runs] == ["codex:one"]
    assert {
        issue_id: list(run_ids) for issue_id, run_ids in checkpoint.issue_runs.items()
    } == {"I_one": ["codex:one"]}

    # A checkpoint handed out earlier is detached from the store's own later
    # commits, not just from the caller's input.
    store.replace_agent_runs(
        [bound_run, agent_run("codex:two", "project:one", issue_id="I_one")],
        {"I_one": ["codex:one", "codex:two"]},
    )
    assert [entry.id for entry in checkpoint.agent_runs] == ["codex:one"]
    assert list(checkpoint.issue_runs["I_one"]) == ["codex:one"]


def test_source_last_good_is_isolated_from_the_collections_it_returned() -> None:
    issues = [issue("I_one", "First")]
    label_colors = {"bug": "ff0000"}
    activity = {"I_one": IssueActivity(comment_count=2)}
    source = _ScriptedSource(issues, label_colors, activity)

    fresh = source.refresh()
    # A consumer of the fresh observation cannot corrupt the retained value.
    source.fail = True
    issues.append(issue("I_rogue", "Rogue"))
    label_colors["bug"] = "00ff00"
    activity["I_rogue"] = IssueActivity(comment_count=9)

    stale = source.refresh()
    assert stale.status == "stale"
    assert [entry.id for entry in stale.issues] == ["I_one"]
    assert dict(stale.label_colors) == {"bug": "ff0000"}
    assert set(stale.issue_activity) == {"I_one"}
    assert fresh.issue_activity["I_one"].comment_count == 2


# --- Direction two: the published value's own collections are immutable ------


def test_published_snapshot_rejects_mutation_of_its_collections() -> None:
    observation = project(
        "project:one",
        issue("I_one", "First"),
        targets=[factories.target("/project:one")],
    )
    store = WorkspaceObservationStore(
        workspace(observation, runs=[agent_run("codex:one", "project:one")])
    )
    checkpoint = store.checkpoint()

    # Each ty ignore below silences the static rejection of exactly the
    # runtime mutation this test proves is refused.
    with pytest.raises(AttributeError):
        checkpoint.projects.append(observation)  # ty: ignore[unresolved-attribute]
    with pytest.raises(TypeError):
        checkpoint.issue_runs["I_rogue"] = ("codex:rogue",)  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        checkpoint.collected_at = "2026-01-01T00:00:00Z"  # ty: ignore[invalid-assignment]

    published = required(store.project("project:one"))
    snapshot = snapshot_of(published)
    with pytest.raises(ValidationError):
        published.display_label = "Mutated"  # ty: ignore[invalid-assignment]
    with pytest.raises(AttributeError):
        snapshot.issues.append(issue("I_rogue", "Rogue"))  # ty: ignore[unresolved-attribute]
    with pytest.raises(TypeError):
        snapshot.label_colors["bug"] = "00ff00"  # ty: ignore[invalid-assignment]
    with pytest.raises(AttributeError):
        snapshot.observation_targets[0].diagnostics.append(  # ty: ignore[unresolved-attribute]
            None
        )


def test_source_observation_rejects_mutation_of_its_collections() -> None:
    source = _ScriptedSource(
        [issue("I_one", "First")],
        {"bug": "ff0000"},
        {"I_one": IssueActivity(comment_count=2)},
    )
    observation = source.refresh()

    # Each ty ignore below silences the static rejection of exactly the
    # runtime mutation this test proves is refused.
    with pytest.raises(AttributeError):
        observation.issues.append(issue("I_rogue", "Rogue"))  # ty: ignore[unresolved-attribute]
    with pytest.raises(TypeError):
        observation.label_colors["bug"] = "00ff00"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        observation.issue_activity["I_one"] = IssueActivity()  # ty: ignore[invalid-assignment]
