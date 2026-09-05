from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from .errors import DashpotError
from .git import Git
from .harnesses import (
    HARNESS_DISPLAY,
    SESSION_OVERRIDE_VARIABLE,
    SessionIdentityClaim,
    native_claims,
    override_claim,
)
from .hook_records import (
    SessionLocation,
    ValidatedSessionIdentity,
    locate_agent_session,
    now_iso,
    reachable_hook_stores,
    validate_session_claim,
)
from .issue_resolution import resolve_issue
from .liveness import session_liveness
from .model import Diagnostic
from .processes import (
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .repository import repository_worktrees, worktree_root
from .work_store import (
    SESSION_KEY,
    ActiveWork,
    RelocationIntent,
    SessionProcess,
    WorkStore,
)

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
        return SessionProcess(pid=self.process.pid, started_at=self.process.started_at)

    @property
    def process_key(self) -> ProcessKey | None:
        if self.process is None:
            return None
        return self.process.pid, self.process.started_at


def identify_agent_session(
    lookup: ProcessLookup = host_process_lookup,
    *,
    environ: Mapping[str, str] | None = None,
    worktree: Path | None = None,
    stores: Sequence[Path] | None = None,
) -> AgentSessionIdentity:
    """Identify the supported Agent Session enclosing this command.

    The harness process in this command's ancestry identifies the session
    when it can be observed. When it cannot, as from a sandbox's isolated
    PID namespace, the session is identified by an Agent Session Identity the
    environment claims, validated against the freshest lifecycle hook record
    of the same harness across the hook ``stores`` reachable from
    ``worktree``; without a Worktree there is nothing to validate against and
    the claim is refused.
    """
    environment = environ if environ is not None else os.environ
    ancestry = observe_agent_ancestry(lookup)
    if ancestry.located is not None:
        harness, process = ancestry.located
        return _process_identity(
            harness,
            process,
            _corroborating_session_id(
                harness, process, environment, worktree, lookup, stores
            ),
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
            validated.append(
                validate_session_claim(claim, worktree, lookup, stores=stores)
            )
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
    stores: Sequence[Path] | None,
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
            confirmed = validate_session_claim(claim, worktree, lookup, stores=stores)
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
    """Start or switch this session's Issue work at the current Worktree.

    A live Agent Session holds one active Agent Run across the linked
    Worktrees of its Git Repository. Its hooks say where it is: when their
    freshest record places it here, a run it holds at another Worktree is a
    relocation and is ended in favour of this one; when they place it
    elsewhere, this command is running where the session is not and is
    refused. A session with no hook record anywhere starts here, as before.
    """
    root = worktree_root(current)
    worktrees = repository_worktrees(root)
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    issue = resolve_issue(root, reference, timeout)
    location = _session_location(session, stores, lookup)
    if location is not None and not _same_worktree(location.worktree, root):
        raise RuntimeError(
            f"{session.session_label} is at {location.worktree} according to "
            f"its freshest {HARNESS_DISPLAY[session.harness]} hook record, not "
            f"at {root}; Issue work is declared where the session itself runs "
            f"(a tool call that changes directory, or a sub-agent, does not "
            f"move the session), so nothing was written"
        )
    unreadable_elsewhere: list[Diagnostic] = []
    for candidate in worktrees:
        if _same_worktree(candidate, root):
            continue
        pending, candidate_diagnostics = _session_work(WorkStore(candidate), session)
        unreadable_elsewhere.extend(candidate_diagnostics)
        if pending is None or pending.relocation is None:
            continue
        intended = Path(pending.relocation.target_worktree)
        if not _same_worktree(intended, root):
            raise RuntimeError(
                f"this Agent Run was prepared to resume at {intended}, not {root}; "
                "the pending run was left unchanged"
            )
        raise RuntimeError(
            f"this Agent Run is still pending relocation from {candidate} to "
            f"{root}; its target hook has not completed the move, so nothing "
            "was written"
        )
    if session.session_id is not None and unreadable_elsewhere:
        raise DashpotError(
            "; ".join(item.message for item in unreadable_elsewhere)
            + "; cannot safely exclude a pending relocation for this Agent "
            "Session, so nothing was written"
        )
    store = WorkStore(root)
    previous, store_diagnostics = _session_work(store, session)
    if session.session_id is not None and store_diagnostics:
        raise DashpotError(
            "; ".join(item.message for item in store_diagnostics)
            + "; cannot safely exclude a pending relocation for this Agent "
            "Session, so nothing was written"
        )
    unreadable = _own_record_diagnostic(store, session.session_key, store_diagnostics)
    if unreadable is not None:
        # Writing beside an unreadable record for this session's own key would
        # leave two records for one session, so this is a refusal instead.
        raise DashpotError(
            f"{unreadable.message}; fix or remove the record before declaring "
            f"Issue work, so this session keeps one record"
        )
    if previous is not None and previous.session_key != session.session_key:
        # The same session was recorded under an earlier key, before its
        # Agent Session Identity was recorded or by the other route; one
        # session keeps one record.
        store.stop(previous.session_key)
    branch = Git(root, timeout=2).maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    store.start(
        ActiveWork(
            session_key=session.session_key,
            harness=session.harness,
            session_label=session.session_label,
            session_process=session.session_process,
            issue_id=issue.id,
            issue_reference=issue.reference,
            binding_provenance="explicit-reference",
            started_at=now_iso(),
            working_directory=str(current),
            branch=branch,
            session_id=session.session_id,
        )
    )
    elsewhere: list[tuple[Path, ActiveWork]] = []
    if location is not None:
        # The hooks place the session here, so a run recorded at another
        # Worktree of the Repository is where it used to be, and nobody is
        # left behind there.
        elsewhere, elsewhere_diagnostics = _stop_elsewhere(session, worktrees, root)
        store_diagnostics.extend(elsewhere_diagnostics)
    if previous is None and elsewhere:
        (former_worktree, former), *rest = elsewhere
        messages = [
            f"switched from {former.issue_reference} at {former_worktree} to "
            f"{issue.reference} at {root} ({issue.id})"
        ]
        elsewhere = rest
    elif previous is None:
        messages = [f"started work on {issue.reference} ({issue.id})"]
    elif previous.issue_id == issue.id:
        messages = [f"already working on {issue.reference}; run restarted"]
    else:
        messages = [
            f"switched from {previous.issue_reference} to {issue.reference} "
            f"({issue.id})"
        ]
    messages.extend(
        f"ended this session's earlier run on {work.issue_reference} at {worktree}"
        for worktree, work in elsewhere
    )
    # Other sessions' unreadable records do not block this start, but they
    # are surfaced rather than dropped, as `work show` already surfaces them.
    messages.extend(diagnostic.message for diagnostic in store_diagnostics)
    return messages


def relocate_issue_work(
    current: Path,
    target: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Prepare this Codex session's active Agent Run for a verified resume."""
    root = worktree_root(current)
    target_root = worktree_root(target)
    worktrees = repository_worktrees(root)
    if not any(_same_worktree(target_root, worktree) for worktree in worktrees):
        raise RuntimeError(
            f"{target_root} is not a linked Worktree of the current Git Repository"
        )
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    if session.harness != "codex":
        raise RuntimeError(
            "work relocate is for a sequential Codex resume; Claude Code moves "
            "its live session with EnterWorktree"
        )
    if session.session_id is None:
        raise RuntimeError(
            "the Codex Agent Session Identity is not confirmed by its lifecycle "
            "hook record; run 'dashpot integrate codex --status'"
        )
    location = _session_location(session, stores, lookup)
    if location is None or not _same_worktree(location.worktree, root):
        observed = "nowhere" if location is None else str(location.worktree)
        raise RuntimeError(
            f"{session.session_label} is at {observed} according to its freshest "
            f"Codex hook record, not at {root}; nothing was written"
        )
    matches: list[tuple[Path, WorkStore, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        store = WorkStore(worktree)
        work, found_diagnostics = _session_work(store, session)
        diagnostics.extend(found_diagnostics)
        if work is not None:
            matches.append((worktree, store, work))
    if diagnostics:
        raise DashpotError(
            "; ".join(item.message for item in diagnostics)
            + "; repair the Work Store before preparing relocation"
        )
    if not matches:
        raise RuntimeError(
            "this Agent Session has no active Issue work to preserve; resume at "
            "the target and run 'dashpot work start' there"
        )
    if len(matches) != 1:
        raise RuntimeError(
            "this Agent Session has Issue work recorded at more than one Worktree; "
            "resolve the work-session-conflict before preparing relocation"
        )
    worktree, store, work = matches[0]
    if not _same_worktree(worktree, root):
        raise RuntimeError(
            f"this Agent Session's active Agent Run is at {worktree}, not {root}; "
            "nothing was written"
        )
    branch = Git(root, timeout=2).maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    if _same_worktree(root, target_root):
        if work.relocation is None:
            raise RuntimeError(
                "the relocation target is this session's current Worktree"
            )
        _replace_current_run(
            store,
            work,
            replace(
                work,
                session_label=session.session_label,
                session_process=session.session_process,
                working_directory=str(current),
                branch=branch,
                session_id=session.session_id,
                relocation=None,
            ),
        )
        return ["cancelled the pending relocation; this Agent Run remains here"]
    _replace_current_run(
        store,
        work,
        replace(
            work,
            session_label=session.session_label,
            session_process=session.session_process,
            working_directory=str(current),
            branch=branch,
            session_id=session.session_id,
            relocation=RelocationIntent(
                target_worktree=str(target_root), requested_at=now_iso()
            ),
        ),
    )
    return [
        f"prepared this Agent Run to resume at {target_root}; exit this Codex "
        f"client before resuming session {session.session_id} there"
    ]


def _replace_current_run(
    store: WorkStore, expected: ActiveWork, replacement: ActiveWork
) -> None:
    """Replace a run unless another management command changed it first."""
    try:
        replaced = store.replace_current(expected, replacement)
    except (OSError, ValueError) as exc:
        raise DashpotError(
            f"cannot safely update this Agent Run for relocation: {exc}"
        ) from exc
    if not replaced:
        raise RuntimeError(
            "this Agent Run changed while relocation was being prepared; "
            "nothing was overwritten, so inspect it with 'dashpot work show'"
        )


def stop_issue_work(
    current: Path,
    *,
    session_key: str | None = None,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """End an active Agent Run of this session, or an orphaned one here.

    Without ``session_key`` the run belongs to the Agent Session enclosing this
    command, which stays alive; it is ended wherever among the Repository's
    Worktrees it is recorded, so a session that moved and simply stops does
    not leave its old Worktree live. With ``session_key`` the run is an
    Orphaned Agent Run left at this Worktree by a session that is no longer
    running, so no enclosing session is required; a session observed to be
    live is refused so its own run cannot be ended from outside. The Work
    Store's authority is unchanged either way.
    """
    root = worktree_root(current)
    store = WorkStore(root)
    if session_key is None:
        worktrees = repository_worktrees(root)
        session = identify_agent_session(
            lookup,
            environ=environ,
            worktree=root,
            stores=reachable_hook_stores(worktrees),
        )
        stopped, diagnostics = _stop_elsewhere(session, worktrees, None)
        # Unreadable records are surfaced beside the outcome: this session's
        # run may be among the records that could not be read.
        warnings = [diagnostic.message for diagnostic in diagnostics]
        if not stopped:
            return ["no active Issue work for this session", *warnings]
        return [
            f"stopped work on {work.issue_reference}"
            + ("" if _same_worktree(worktree, root) else f" at {worktree}")
            for worktree, work in stopped
        ] + warnings
    previous, diagnostics = _session_work_by_key(store, session_key)
    if previous is None:
        unreadable = _own_record_diagnostic(store, session_key, diagnostics)
        if unreadable is not None:
            # An unreadable record cannot answer whether its session is live,
            # so ending it from outside is refused rather than guessed at.
            raise DashpotError(
                f"{unreadable.message}; remove the record by hand once the "
                f"session is confirmed over"
            )
        return [f"no active Issue work recorded for session {session_key}"]
    if _recorded_session_is_live(previous, root, lookup):
        raise RuntimeError(
            f"session {session_key} is still running; run 'dashpot work stop' inside it"
        )
    if not store.stop(session_key):
        return [f"no active Issue work recorded for session {session_key}"]
    return [
        f"stopped orphaned work on {previous.issue_reference} for "
        f"{previous.session_label}"
    ]


def _recorded_session_is_live(
    work: ActiveWork, root: Path, lookup: ProcessLookup
) -> bool:
    """Whether the session that recorded a run is still observed live.

    A run recorded with its host process is probed directly. One recorded by
    Agent Session Identity alone - the sandboxed route - has only its hook
    records to answer from: the freshest that is neither ended nor gone
    places a session that may still be running, and an unreadable record is
    not evidence that it is over.
    """
    if work.session_process is not None:
        return session_liveness(work.session_process.key, lookup).liveness == "live"
    if work.session_id is None:
        return False
    try:
        location = locate_agent_session(
            reachable_hook_stores(repository_worktrees(root)),
            lookup,
            session_id=work.session_id,
        )
    except ValueError as exc:
        raise RuntimeError(
            f"the lifecycle hook record for {work.session_label} cannot be "
            f"read: {exc}; run 'dashpot integrate {work.harness} --status'"
        ) from exc
    return location is not None and location.record.outcome not in {"ended", "gone"}


def show_issue_work(current: Path) -> list[str]:
    """Read the active Agent Runs recorded at the current Worktree."""
    root = worktree_root(current)
    active, diagnostics = WorkStore(root).active()
    messages = [
        f"{work.session_label}: {work.issue_reference} ({work.issue_id}) "
        f"since {work.started_at}"
        + (
            f"; relocation pending to {work.relocation.target_worktree}"
            if work.relocation is not None
            else ""
        )
        for work in active
    ]
    messages.extend(diagnostic.message for diagnostic in diagnostics)
    if not messages:
        messages = ["no active Issue work at this worktree"]
    return messages


def _session_location(
    session: AgentSessionIdentity, stores: Sequence[Path], lookup: ProcessLookup
) -> SessionLocation | None:
    """Where the session's hooks last placed it, if they have placed it at all.

    A record that is ended or whose process is gone describes a session that
    is over, never where this live one is.
    """
    if session.session_id is None and session.process_key is None:
        return None
    try:
        location = locate_agent_session(
            stores,
            lookup,
            session_id=session.session_id,
            process_key=session.process_key,
        )
    except ValueError as exc:
        raise RuntimeError(
            f"the lifecycle hook record for {session.session_label} cannot be "
            f"read: {exc}; run 'dashpot integrate {session.harness} --status'"
        ) from exc
    if location is None or location.record.outcome in {"ended", "gone"}:
        return None
    return location


def _stop_elsewhere(
    session: AgentSessionIdentity, worktrees: Sequence[Path], here: Path | None
) -> tuple[list[tuple[Path, ActiveWork]], list[Diagnostic]]:
    """End the session's active runs at every Worktree other than ``here``.

    Each Worktree's unreadable Work Store records come back beside the runs:
    a corrupt record could hide the very run this session is looking for.
    """
    stopped: list[tuple[Path, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        if here is not None and _same_worktree(worktree, here):
            continue
        store = WorkStore(worktree)
        work, store_diagnostics = _session_work(store, session)
        diagnostics.extend(store_diagnostics)
        if work is not None and store.stop(work.session_key):
            stopped.append((worktree, work))
    return stopped, diagnostics


def _same_worktree(candidate: Path, worktree: Path) -> bool:
    try:
        return candidate.resolve() == worktree.resolve()
    except OSError:
        return False


def _session_work_by_key(
    store: WorkStore, session_key: str
) -> tuple[ActiveWork | None, list[Diagnostic]]:
    """One session's recorded run by key, with the store's diagnostics."""
    active, diagnostics = store.active()
    found = next((work for work in active if work.session_key == session_key), None)
    return found, diagnostics


def _own_record_diagnostic(
    store: WorkStore, session_key: str, diagnostics: Sequence[Diagnostic]
) -> Diagnostic | None:
    """The diagnostic for exactly this session key's record, if it has one."""
    if not SESSION_KEY.fullmatch(session_key):
        return None
    source = f"work:{store.record_path(session_key)}"
    return next(
        (diagnostic for diagnostic in diagnostics if diagnostic.source == source),
        None,
    )


def _session_work(
    store: WorkStore, session: AgentSessionIdentity
) -> tuple[ActiveWork | None, list[Diagnostic]]:
    """The session's active run, whichever identity it was recorded under.

    The store's diagnostics ride along instead of being dropped: an
    unreadable record is exactly where this session's run could be hiding.
    """
    active, diagnostics = store.active()
    for work in active:
        if work.session_key == session.session_key:
            return work, diagnostics
    for work in active:
        if work.harness != session.harness:
            continue
        if session.session_id is not None and work.session_id == session.session_id:
            return work, diagnostics
        if (
            session.session_process is not None
            and work.session_process == session.session_process
        ):
            return work, diagnostics
    return None, diagnostics
