"""Shared builders for the fixtures the test modules used to duplicate.

Each factory carries one set of defaults; a module whose assertions depend on
different values passes them explicitly (or keeps a thin local wrapper), so
migrating onto a factory never changes what a test asserts.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dashpot.agents import ProcessIdentity, session_directory, write_hook_record
from dashpot.issue_profile import IssueProfile
from dashpot.model import (
    AgentRun,
    Branch,
    Diagnostic,
    ObservationTarget,
    ProjectObservation,
    ProjectSnapshot,
    RunState,
    SourceStatus,
    TargetRole,
    WorkspaceSnapshot,
)

NOW = "2026-08-27T03:00:00Z"

# The moments a published hook record was last active, before and after the
# Work Store facts most tests stamp at 2026-08-30T03:3x.
EARLIER = "2026-08-30T03:34:35.830802Z"
LATER = "2026-08-30T03:40:00.000000Z"

CODEX = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")
CLAUDE = ProcessIdentity(7777, 1, "claude", "Tue Aug 25 02:00:00 2026")

_ISSUES_FIXTURE = Path(__file__).parent / "fixtures" / "local-markdown" / "ISSUES.md"

# Sentinel distinguishing "derive a default" from an explicit ``None``.
_DERIVED: Any = object()


# --- Git repositories --------------------------------------------------------


def git(root: Path, *args: str) -> str:
    """Run ``git`` in ``root`` and return its stripped stdout."""
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def init_repository(root: Path, *, origin: str | None = None) -> Path:
    """Create ``root`` and initialise an empty Git repository there."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    if origin is not None:
        git(root, "remote", "add", "origin", origin)
    return root


# --- Project configuration ---------------------------------------------------


def write_project_config(
    root: Path,
    *,
    project_id: str = "project:test",
    display_label: str = "Test",
    repository_id: str = "repository:test",
    issue_source: dict[str, Any] | None = None,
) -> None:
    """Write a complete ``.dashpot/config.json`` for the Project at ``root``."""
    (root / ".dashpot").mkdir(parents=True, exist_ok=True)
    (root / ".dashpot" / "config.json").write_text(
        json.dumps(
            {
                "projectId": project_id,
                "displayLabel": display_label,
                "repositoryId": repository_id,
                "issueSource": issue_source or {"kind": "markdown", "path": "issues"},
            }
        )
    )


def write_config_marker(root: Path) -> None:
    """Mark ``root`` as configured with an empty ``.dashpot/config.json``."""
    (root / ".dashpot").mkdir(parents=True, exist_ok=True)
    (root / ".dashpot" / "config.json").write_text("{}")


# --- Local Issue documents ---------------------------------------------------

# The metadata a hand-written Local Issue carries beyond its identity fields:
# no labels, no relationships, and a bare author.
PLAIN_ISSUE_METADATA: dict[str, Any] = {
    "labels": [],
    "assignees": [],
    "author": "ned",
    "relationships": {
        "parent": None,
        "subIssues": [],
        "blockedBy": [],
        "blocking": [],
    },
    "issueType": None,
    "milestone": None,
}


def local_issue_document(
    *,
    issue_id: str,
    reference: str,
    title: str,
    number: int = 9,
    body: str = "A complete local Issue.",
    **overrides: Any,
) -> str:
    """Build a Local Issue document from the shared fixture's front matter."""
    fixture_lines = _ISSUES_FIXTURE.read_text().splitlines()
    front_matter_end = fixture_lines.index("---", 1)
    metadata = json.loads("\n".join(fixture_lines[1:front_matter_end]))
    metadata["id"] = issue_id
    metadata["number"] = number
    metadata["reference"] = reference
    metadata.update(overrides)
    return "\n".join(
        ["---", json.dumps(metadata, indent=2), "---", f"# {title}", "", body, ""]
    )


def issue_document(*, issue_id: str, number: int, reference: str, title: str) -> str:
    """Build the plain Local Issue document the Work-family tests share."""
    return local_issue_document(
        issue_id=issue_id,
        number=number,
        reference=reference,
        title=title,
        body="Body.",
        **PLAIN_ISSUE_METADATA,
    )


# ``dashpot_project``'s default Issues, and the pair the Worktree-protocol
# acceptance tests resolve by number 35/36.
DEFAULT_PROJECT_ISSUES: dict[str, dict[str, Any]] = {
    "build-observer.md": {
        "issue_id": "I_observer",
        "number": 1,
        "reference": "build-observer",
        "title": "Build observer",
    },
    "fix-crash.md": {
        "issue_id": "I_crash",
        "number": 2,
        "reference": "fix-crash",
        "title": "Fix crash",
    },
}
WORKTREE_PROTOCOL_ISSUES: dict[str, dict[str, Any]] = {
    "worktree-protocol.md": {
        "issue_id": "I_35",
        "number": 35,
        "reference": "worktree-protocol",
        "title": "Worktree protocol",
    },
    "other.md": {
        "issue_id": "I_36",
        "number": 36,
        "reference": "other",
        "title": "Other",
    },
}


def write_issues(root: Path, issues: Mapping[str, Mapping[str, Any]]) -> None:
    """Write each Local Issue document into ``root``'s ``issues`` directory."""
    directory = root / "issues"
    directory.mkdir(exist_ok=True)
    for filename, spec in issues.items():
        (directory / filename).write_text(issue_document(**spec))


def dashpot_project(
    root: Path,
    *,
    issues: Mapping[str, Mapping[str, Any]] | None = None,
    issues_path: str = "issues",
    project_id: str = "project:test",
    display_label: str = "Test",
    repository_id: str = "repository:test",
) -> Path:
    """Initialise a configured Local Markdown Project repository at ``root``.

    ``issues_path`` names the configured Issue Source path; the documents are
    always written under ``issues``, so a diverging path is an unavailable
    source by construction.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    write_project_config(
        root,
        project_id=project_id,
        display_label=display_label,
        repository_id=repository_id,
        issue_source={"kind": "markdown", "path": issues_path},
    )
    write_issues(root, DEFAULT_PROJECT_ISSUES if issues is None else issues)
    return root


# --- Hook records ------------------------------------------------------------

_EVENT_BY_STATE = {"running": "UserPromptSubmit", "waiting": "Stop", "ended": "Stop"}


def hook_record_document(
    root: Path | str,
    session_id: str,
    harness: str = "codex",
    process: ProcessIdentity | None = None,
    *,
    state: str = "running",
    at: str = EARLIER,
    cwd: str | None = None,
    branch: str | None = "main",
    event: str | None = None,
) -> dict[str, Any]:
    """Build a v2 hook record placing ``session_id`` at ``root``."""
    return {
        "version": 2,
        "sessionId": session_id,
        "harness": harness,
        "state": state,
        "cwd": cwd if cwd is not None else str(root),
        "repositoryRoot": str(root),
        "branch": branch,
        "event": event or _EVENT_BY_STATE[state],
        "lastActivityAt": at,
        "sessionProcess": process.as_record() if process else None,
    }


def hook_record(
    root: Path,
    session_id: str,
    harness: str,
    process: ProcessIdentity | None,
    *,
    state: str = "running",
    at: str = EARLIER,
    store: Path | None = None,
) -> Path:
    """Publish a hook record placing the session at ``root``.

    It lands in ``root``'s own store unless ``store`` names another, as the
    global store does for a Worktree whose checkout predates configuration.
    """
    return write_hook_record(
        hook_record_document(root, session_id, harness, process, state=state, at=at),
        store if store is not None else session_directory(root),
    )


def legacy_ended_record(root: Path, session_id: str, harness: str) -> None:
    """Write a pre-``lastActivityAt`` ended record straight into the store."""
    directory = session_directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{session_id}.json").write_text(
        json.dumps(
            {
                "version": 2,
                "sessionId": session_id,
                "harness": harness,
                "state": "ended",
                "cwd": str(root),
                "repositoryRoot": str(root),
                "event": "SessionEnd",
            }
        )
    )


# --- Read-model snapshots ----------------------------------------------------


def target(
    path: str,
    *,
    role: TargetRole = "main",
    branch: str | None = "main",
    head: str = "abcdef1234567",
    dirty: bool | None = False,
    available: bool = True,
    elapsed_ms: int = 3,
) -> ObservationTarget:
    """Build an observed Observation Target at ``path``."""
    return ObservationTarget(
        path=path,
        head=head,
        branch=branch,
        detached=branch is None,
        dirty=dirty,
        availability="available" if available else "unavailable",
        elapsed_ms=elapsed_ms,
        diagnostics=[],
        role=role,
    )


def project(
    project_id: str,
    *issues: IssueProfile,
    label: str | None = None,
    repository_id: str | None = None,
    targets: Sequence[ObservationTarget] | None = None,
    branches: Sequence[Branch] | None = None,
    anchors: Sequence[str] | None = None,
    status: SourceStatus = "fresh",
    target_status: SourceStatus = "fresh",
    last_good_at: str | None = _DERIVED,
    diagnostics: Sequence[Diagnostic] = (),
    elapsed_ms: int = 3,
    now: str = NOW,
    missing: bool = False,
) -> ProjectObservation:
    """Build a Project Observation whose snapshot carries ``issues``."""
    display_label = label or project_id.removeprefix("project:").title()
    repository = repository_id or f"repository:{project_id}"
    if last_good_at is _DERIVED:
        last_good_at = now if status != "unavailable" else None
    anchor_paths = list(anchors or (f"/{project_id}",))
    snapshot = None
    if not missing:
        snapshot = ProjectSnapshot(
            project_id=project_id,
            display_label=display_label,
            repository_id=repository,
            collected_at=now,
            issue_source_status=status,
            issue_source_attempted_at=now,
            issue_source_last_good_at=last_good_at,
            observation_targets=list(targets or []),
            issues=list(issues),
            diagnostics=list(diagnostics),
            target_status=target_status,
            branches=list(branches or []),
        )
    return ProjectObservation(
        project_id=project_id,
        display_label=display_label,
        repository_id=repository,
        workspaces=["test"],
        anchors=anchor_paths,
        primary_anchor=anchor_paths[0],
        status="unavailable" if missing else status,
        elapsed_ms=elapsed_ms,
        snapshot=snapshot,
        diagnostics=[],
    )


def workspace(
    *projects: ProjectObservation,
    runs: list[AgentRun] | None = None,
    issue_runs: dict[str, list[str]] | None = None,
    diagnostics: Sequence[Diagnostic] = (),
    elapsed_ms: int = 9,
    now: str = NOW,
) -> WorkspaceSnapshot:
    """Build a Workspace Snapshot over already-built Project Observations."""
    return WorkspaceSnapshot(
        collected_at=now,
        elapsed_ms=elapsed_ms,
        projects=list(projects),
        agent_runs=runs or [],
        issue_runs=issue_runs or {},
        diagnostics=list(diagnostics),
    )


def agent_run(
    run_id: str,
    project_id: str = "project:alpha",
    *,
    harness: str = "codex",
    state: RunState = "waiting",
    issue_id: str | None = None,
    hint: str | None = None,
    branch: str | None = "main",
    target_path: str | None = None,
    working_directory: str | None = _DERIVED,
    last_activity_at: str | None = NOW,
    process_or_session: str | None = None,
) -> AgentRun:
    """Build an Agent Run observed at ``target_path`` of ``project_id``."""
    observed_at = target_path or f"/{project_id}"
    if working_directory is _DERIVED:
        working_directory = observed_at
    return AgentRun(
        id=run_id,
        harness=harness,
        process_or_session=process_or_session or run_id,
        state=state,
        observation_target=observed_at,
        observation_project_id=project_id,
        branch=branch,
        issue_id=issue_id,
        issue_reference_hint=hint,
        working_directory=working_directory,
        last_activity_at=last_activity_at,
    )


def session(
    run_id: str, project_id: str, target_path: str, state: RunState = "waiting"
) -> AgentRun:
    """Build the bare session-shaped Agent Run the worktree panes list."""
    return agent_run(
        run_id,
        project_id,
        state=state,
        target_path=target_path,
        working_directory=None,
        last_activity_at=None,
    )
