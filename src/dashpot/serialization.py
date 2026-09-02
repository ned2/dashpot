"""Own the headless JSON contract: one document shape per command.

The key set of every ``--json`` document is a stable, first-release contract
([#78](https://github.com/ned2/dashpot/issues/78)): every documented field
is present, keys are camelCase, an unknown value is an explicit ``null``
rather than an omitted key, and a shape change is a compatibility change.
Pydantic's dump is the mechanism, never the authority: ``tests/test_serialization.py``
pins each command's key set independently of the models' defaults.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .cleanup import CleanupPreview, CleanupReport
from .issue_profile import IssueProfile
from .model import WorkspaceSnapshot
from .worktrees import WorktreePlan, WorktreeRemovability


def _document(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True)


def snapshot_document(snapshot: WorkspaceSnapshot) -> dict[str, Any]:
    """The ``dashpot --json`` document: one complete Workspace Snapshot."""
    return _document(snapshot)


def issue_document(issue: IssueProfile) -> dict[str, Any]:
    """The ``dashpot issue show --json`` document: the complete Issue Profile."""
    return _document(issue)


def worktree_plan_document(plan: WorktreePlan) -> dict[str, Any]:
    """The ``dashpot worktree create --json`` document."""
    return _document(plan)


def removability_document(report: WorktreeRemovability) -> dict[str, Any]:
    """The ``dashpot worktree check --json`` document."""
    return _document(report)


def render_json(
    document: dict[str, Any] | list[dict[str, Any]], *, compact: bool = False
) -> str:
    """Render a command document, or a list of them, as JSON text."""
    return json.dumps(document, indent=None if compact else 2)


def cleanup_preview_document(preview: CleanupPreview) -> dict[str, Any]:
    """The preview a Cleanup command confirms against, as its JSON document."""
    return _document(preview)


def cleanup_report_document(report: CleanupReport) -> dict[str, Any]:
    """The document of a performed Cleanup command: each target's outcome."""
    return _document(report)
