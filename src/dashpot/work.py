from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .agents import (
    ProcessIdentity,
    ProcessLookup,
    ValidatedSessionIdentity,
    host_process_lookup,
    now_iso,
    observe_agent_ancestry,
    session_liveness,
    validate_session_claim,
)
from .github_issues import GitHubIssuesSource
from .harnesses import (
    HARNESS_DISPLAY,
    SESSION_OVERRIDE_VARIABLE,
    SessionIdentityClaim,
    native_claims,
    override_claim,
)
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


IdentityRoute = Literal["process", "session"]


@dataclass(frozen=True, slots=True)
class AgentSessionIdentity:
    """The Agent Session enclosing a command, however it was identified.

    ``route`` records which evidence identified it: the harness process found
    in this command's ancestry, or a claimed Agent Session Identity that the
    harness's hook record confirmed because that ancestry is hidden. Either
    way the process identity is carried when known, so Session Liveness and
    orphan detection do not depend on the route.
    """

    harness: str
    session_key: str
    session_label: str
    process: ProcessIdentity | None
    session_id: str | None = None
    route: IdentityRoute = "process"

    @property
    def session_process(self) -> SessionProcess | None:
        if self.process is None:
            return None
        return SessionProcess(self.process.pid, self.process.started_at)


def identify_agent_session(
    lookup: ProcessLookup = host_process_lookup,
    *,
    environ: Mapping[str, str] | None = None,
    worktree: Path | None = None,
) -> AgentSessionIdentity:
    """Identify the supported Agent Session enclosing this command.

    The harness process in this command's ancestry identifies the session
    when it can be observed. When it cannot, as from a sandbox's isolated
    PID namespace, the session is identified by an Agent Session Identity the
    environment claims, validated against the lifecycle hook record of the
    same harness at ``worktree``; without a Worktree there is nothing to
    validate against and the claim is refused.
    """
    environment = environ if environ is not None else os.environ
    ancestry = observe_agent_ancestry(lookup)
    if ancestry.located is not None:
        harness, process = ancestry.located
        return _process_identity(
            harness,
            process,
            _corroborating_session_id(harness, process, environment, worktree, lookup),
        )
    claims = _session_claims(environment)
    if not claims:
        raise RuntimeError(_no_session_message(ancestry.unobservable_reason))
    if worktree is None:
        raise RuntimeError(
            "an Agent Session Identity claimed by the environment can only be "
            "validated at a Worktree with a Project-local hook record store"
        )
    validated: list[ValidatedSessionIdentity] = []
    failures: list[str] = []
    for claim in claims:
        try:
            validated.append(validate_session_claim(claim, worktree, lookup))
        except RuntimeError as exc:
            failures.append(str(exc))
    if len(validated) == 1:
        return _session_identity(validated[0])
    if validated:
        names = " and ".join(
            f"{HARNESS_DISPLAY[item.harness]} session {item.session_id}"
            for item in validated
        )
        raise RuntimeError(
            f"the environment claims more than one live Agent Session ({names}); "
            f"set {SESSION_OVERRIDE_VARIABLE}=<harness>:<session id> to say which "
            f"session this command belongs to"
        )
    raise RuntimeError(
        _no_session_message(ancestry.unobservable_reason) + "; " + "; ".join(failures)
    )


def _session_claims(environment: Mapping[str, str]) -> list[SessionIdentityClaim]:
    """The identities to validate: an explicit override alone, else every native claim."""
    explicit = override_claim(environment)
    if explicit is not None:
        return [explicit]
    return native_claims(environment)


def _no_session_message(unobservable_reason: str | None) -> str:
    message = (
        "no supported agent session encloses this command; Issue work opt-in "
        "must run from inside a running Codex or Claude Code session"
    )
    if unobservable_reason == "isolated-namespace":
        message += (
            " (this command runs in a sandbox's isolated process namespace, so "
            "the harness must be identified by the Agent Session Identity its "
            "lifecycle hooks publish; check 'dashpot integrate <harness> --status')"
        )
    elif unobservable_reason is not None:
        message += (
            f" (the enclosing process could not be observed: {unobservable_reason})"
        )
    return message


def _corroborating_session_id(
    harness: str,
    process: ProcessIdentity,
    environment: Mapping[str, str],
    worktree: Path | None,
    lookup: ProcessLookup,
) -> str | None:
    """A claimed identity of the located harness whose hook record agrees.

    The located process is authoritative here; a claim only adds the Agent
    Session Identity to the record, and one that disagrees is left out.
    """
    if worktree is None:
        return None
    for claim in _session_claims(environment):
        if claim.harness != harness:
            continue
        try:
            confirmed = validate_session_claim(claim, worktree, lookup)
        except RuntimeError:
            continue
        if confirmed.process is None or confirmed.process.pid == process.pid:
            return confirmed.session_id
    return None


def _process_identity(
    harness: str, process: ProcessIdentity, session_id: str | None
) -> AgentSessionIdentity:
    digest = hashlib.sha256(process.started_at.encode()).hexdigest()[:8]
    return AgentSessionIdentity(
        harness=harness,
        session_key=f"{harness}-{process.pid}-{digest}",
        session_label=f"{harness} pid {process.pid}",
        process=process,
        session_id=session_id,
        route="process",
    )


def _session_identity(confirmed: ValidatedSessionIdentity) -> AgentSessionIdentity:
    """Identify a session by its confirmed Agent Session Identity.

    The hook record's process identity, published from the host by the hook,
    keys the record exactly as the process route would, so a session's key
    does not depend on whether its commands are sandboxed.
    """
    if confirmed.process is not None:
        identity = _process_identity(
            confirmed.harness, confirmed.process, confirmed.session_id
        )
        return AgentSessionIdentity(
            identity.harness,
            identity.session_key,
            identity.session_label,
            identity.process,
            identity.session_id,
            "session",
        )
    digest = hashlib.sha256(confirmed.session_id.encode()).hexdigest()[:12]
    return AgentSessionIdentity(
        harness=confirmed.harness,
        session_key=f"{confirmed.harness}-session-{digest}",
        session_label=f"{confirmed.harness} session {confirmed.session_id}",
        process=None,
        session_id=confirmed.session_id,
        route="session",
    )


def start_issue_work(
    current: Path,
    reference: str,
    *,
    timeout: float = 10,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Start or switch this session's Issue work at the current Worktree."""
    root = worktree_root(current)
    session = identify_agent_session(lookup, environ=environ, worktree=root)
    issue = _resolve_issue(root, reference, timeout)
    store = WorkStore(root)
    previous = _session_work(store, session)
    if previous is not None and previous.session_key != session.session_key:
        # The same session was recorded under an earlier key, before its
        # Agent Session Identity was recorded or by the other route; one
        # session keeps one record.
        store.stop(previous.session_key)
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
            session_process=session.session_process,
            issue_id=issue["id"],
            issue_reference=issue["reference"],
            binding_provenance="explicit-reference",
            started_at=now_iso(),
            working_directory=str(current),
            branch=branch,
            session_id=session.session_id,
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
    environ: Mapping[str, str] | None = None,
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
        session = identify_agent_session(lookup, environ=environ, worktree=root)
        previous = _session_work(store, session)
        if previous is None or not store.stop(previous.session_key):
            return ["no active Issue work for this session"]
        return [f"stopped work on {previous.issue_reference}"]
    previous = _session_work_by_key(store, session_key)
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


def _session_work_by_key(store: WorkStore, session_key: str) -> ActiveWork | None:
    active, _ = store.active()
    return next((work for work in active if work.session_key == session_key), None)


def _session_work(store: WorkStore, session: AgentSessionIdentity) -> ActiveWork | None:
    """The session's active run, whichever identity it was recorded under."""
    active, _ = store.active()
    for work in active:
        if work.session_key == session.session_key:
            return work
    for work in active:
        if work.harness != session.harness:
            continue
        if session.session_id is not None and work.session_id == session.session_id:
            return work
        if (
            session.session_process is not None
            and work.session_process == session.session_process
        ):
            return work
    return None


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
