from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agents import (
    ProcessIdentity,
    ProcessLookup,
    host_process_lookup,
    nearest_agent_process,
    now_iso,
    session_liveness,
)
from .github_issues import GitHubIssuesSource
from .issue_sources import IssueSource
from .local_markdown_issues import LocalMarkdownIssuesSource
from .project_config import (
    GitHubIssueSourceConfig,
    LocalMarkdownIssueSourceConfig,
    load_project_config,
)
from .repository import git, github_repo_from_remote, worktree_root
from .work_store import ActiveWork, SessionProcess, WorkStore

ISSUE_NUMBER = re.compile(r"^#?([1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class AgentSessionIdentity:
    harness: str
    session_key: str
    session_label: str
    process: ProcessIdentity


def identify_agent_session(
    lookup: ProcessLookup = host_process_lookup,
) -> AgentSessionIdentity:
    """Identify the supported Agent Session enclosing this command."""
    located = nearest_agent_process(lookup)
    if located is None:
        raise RuntimeError(
            "no supported agent session encloses this command; Issue work "
            "opt-in must run from inside a running Codex or Claude Code "
            "session"
        )
    harness, process = located
    digest = hashlib.sha256(process.started_at.encode()).hexdigest()[:8]
    return AgentSessionIdentity(
        harness=harness,
        session_key=f"{harness}-{process.pid}-{digest}",
        session_label=f"{harness} pid {process.pid}",
        process=process,
    )


def start_issue_work(
    current: Path,
    reference: str,
    *,
    timeout: float = 10,
    lookup: ProcessLookup = host_process_lookup,
) -> list[str]:
    """Start or switch this session's Issue work at the current Worktree."""
    session = identify_agent_session(lookup)
    root = worktree_root(current)
    issue = _resolve_issue(root, reference, timeout)
    store = WorkStore(root)
    previous = _session_work(store, session.session_key)
    try:
        branch: str | None = git(
            root, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=2
        )
    except RuntimeError:
        branch = None
    store.start(
        ActiveWork(
            session_key=session.session_key,
            harness=session.harness,
            session_label=session.session_label,
            session_process=SessionProcess(
                session.process.pid, session.process.started_at
            ),
            issue_id=issue["id"],
            issue_reference=issue["reference"],
            binding_provenance="explicit-reference",
            started_at=now_iso(),
            working_directory=str(current),
            branch=branch,
        )
    )
    if previous is None:
        return [f"started work on {issue['reference']} ({issue['id']})"]
    if previous.issue_id == issue["id"]:
        return [f"already working on {issue['reference']}; run restarted"]
    return [
        f"switched from {previous.issue_reference} to {issue['reference']} "
        f"({issue['id']})"
    ]


def stop_issue_work(
    current: Path,
    *,
    session_key: str | None = None,
    lookup: ProcessLookup = host_process_lookup,
) -> list[str]:
    """End an active Agent Run recorded at the current Worktree.

    Without ``session_key`` the run belongs to the Agent Session enclosing this
    command, which stays alive. With ``session_key`` the run is an Orphaned
    Agent Run left by a session that is no longer running, so no enclosing
    session is required; a session observed to be live is refused so its own
    run cannot be ended from outside. The Work Store's authority is unchanged
    either way.
    """
    root = worktree_root(current)
    store = WorkStore(root)
    if session_key is None:
        session = identify_agent_session(lookup)
        previous = _session_work(store, session.session_key)
        if not store.stop(session.session_key) or previous is None:
            return ["no active Issue work for this session"]
        return [f"stopped work on {previous.issue_reference}"]
    previous = _session_work(store, session_key)
    if previous is None:
        return [f"no active Issue work recorded for session {session_key}"]
    if (
        previous.session_process is not None
        and session_liveness(previous.session_process.as_record(), lookup).liveness
        == "live"
    ):
        raise RuntimeError(
            f"session {session_key} is still running; run 'dashpot work stop' inside it"
        )
    if not store.stop(session_key):
        return [f"no active Issue work recorded for session {session_key}"]
    return [
        f"stopped orphaned work on {previous.issue_reference} for "
        f"{previous.session_label}"
    ]


def show_issue_work(current: Path) -> list[str]:
    """Read the active Agent Runs recorded at the current Worktree."""
    root = worktree_root(current)
    active, diagnostics = WorkStore(root).active()
    messages = [
        f"{work.session_label}: {work.issue_reference} ({work.issue_id}) "
        f"since {work.started_at}"
        for work in active
    ]
    messages.extend(diagnostic.message for diagnostic in diagnostics)
    if not messages:
        messages = ["no active Issue work at this worktree"]
    return messages


def _session_work(store: WorkStore, session_key: str) -> ActiveWork | None:
    active, _ = store.active()
    return next((work for work in active if work.session_key == session_key), None)


def _resolve_issue(root: Path, reference: str, timeout: float) -> dict[str, Any]:
    """Resolve a mutable Issue Reference to exactly one observed Issue."""
    config = load_project_config(root)
    if isinstance(config.issue_source, GitHubIssueSourceConfig):
        if not github_repo_from_remote(root):
            raise RuntimeError(
                "a GitHub Issue Source requires this Worktree to have a "
                "GitHub origin remote"
            )
        source: IssueSource = GitHubIssuesSource(
            root,
            project_id=config.project_id,
            repository_id=config.repository_id,
            timeout=timeout,
        )
    elif isinstance(config.issue_source, LocalMarkdownIssueSourceConfig):
        source = LocalMarkdownIssuesSource(
            root,
            project_id=config.project_id,
            issues_path=Path(config.issue_source.path),
        )
    else:  # pragma: no cover - exhaustive guard for future source kinds.
        raise RuntimeError("unsupported configured Issue Source")
    observation = source.refresh()
    if observation.status != "fresh":
        details = "; ".join(
            diagnostic.message for diagnostic in observation.diagnostics
        )
        raise RuntimeError(
            f"cannot resolve Issue Reference while the Issue Source is "
            f"{observation.status}: {details or 'no diagnostics'}"
        )
    number_match = ISSUE_NUMBER.fullmatch(reference)
    if number_match:
        number = int(number_match.group(1))
        matches = [issue for issue in observation.issues if issue["number"] == number]
    else:
        matches = [
            issue for issue in observation.issues if issue["reference"] == reference
        ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise RuntimeError(f"Issue Reference {reference!r} is ambiguous")
    raise RuntimeError(
        f"Issue Reference {reference!r} did not match an Issue in this Project"
    )
