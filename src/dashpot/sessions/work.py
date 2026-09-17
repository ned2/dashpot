from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ..core.errors import DashpotError
from ..core.git import Git
from ..core.model import Diagnostic
from ..core.timestamps import utc_now
from ..issues.issue_resolution import resolve_issue
from ..repository import repository_worktrees, same_path, worktree_root
from .harnesses import (
    HARNESS_DISPLAY,
    SESSION_OVERRIDE_VARIABLE,
    SessionIdentityClaim,
    native_claims,
    override_claim,
)
from .hook_claims import ValidatedSessionIdentity, validate_session_claim
from .hook_scan import (
    SessionLocation,
    locate_agent_session,
    reachable_hook_stores,
)
from .liveness import session_liveness
from .processes import (
    ProcessIdentity,
    ProcessKey,
    ProcessLookup,
    host_process_lookup,
    observe_agent_ancestry,
)
from .session_matching import SessionEvidence
from .work_store import (
    SESSION_KEY,
    ActiveWork,
    RelocationIntent,
    SessionProcess,
    WorkStore,
)


@dataclass(frozen=True, slots=True)
class AgentSessionIdentity:
    """Represent a confirmed Agent Session and its corroborating process evidence."""

    harness: str
    session_key: str
    session_label: str
    process: ProcessIdentity | None
    session_id: str | None = None

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
    """Identify the enclosing session by a hook-confirmed native identity."""
    environment = environ if environ is not None else os.environ
    ancestry = observe_agent_ancestry(lookup)
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
        confirmed = validated[0]
        if ancestry.located is not None:
            harness, process = ancestry.located
            if harness != confirmed.harness or (
                confirmed.process is not None and confirmed.process.key != process.key
            ):
                raise RuntimeError(
                    "the claimed Agent Session Identity does not corroborate the "
                    "enclosing harness process; nothing was written"
                )
            return _process_identity(harness, process, confirmed.session_id)
        return _session_identity(confirmed)
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


def _process_identity(
    harness: str, process: ProcessIdentity, session_id: str
) -> AgentSessionIdentity:
    return AgentSessionIdentity(
        harness=harness,
        session_key=SessionEvidence(harness, session_id).storage_key(),
        session_label=f"{harness} pid {process.pid}",
        process=process,
        session_id=session_id,
    )


def _session_identity(confirmed: ValidatedSessionIdentity) -> AgentSessionIdentity:
    """Identify a session by its confirmed native identity on either route."""
    return AgentSessionIdentity(
        harness=confirmed.harness,
        session_key=SessionEvidence(
            confirmed.harness, confirmed.session_id
        ).storage_key(),
        session_label=(
            f"{confirmed.harness} pid {confirmed.process.pid}"
            if confirmed.process is not None
            else f"{confirmed.harness} session {confirmed.session_id}"
        ),
        process=confirmed.process,
        session_id=confirmed.session_id,
    )


def start_issue_work(
    current: Path,
    reference: str,
    *,
    timeout: float = 10,
    lookup: ProcessLookup = host_process_lookup,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Start or switch confirmed Issue work at the session's observed Worktree."""
    root = worktree_root(current)
    worktrees = repository_worktrees(root)
    stores = reachable_hook_stores(worktrees)
    session = identify_agent_session(
        lookup, environ=environ, worktree=root, stores=stores
    )
    issue = resolve_issue(root, reference, timeout)
    location = _session_location(session, stores, lookup)
    if location is None:
        raise RuntimeError(
            "this Agent Session has no current hook location; nothing was written"
        )
    if not same_path(location.worktree, root):
        raise RuntimeError(
            f"{session.session_label} is at {location.worktree} according to "
            f"its freshest {HARNESS_DISPLAY[session.harness]} hook record, not "
            f"at {root}; Issue work is declared where the session itself runs "
            f"(a tool call that changes directory, or a sub-agent, does not "
            f"move the session), so nothing was written"
        )
    unreadable_elsewhere: list[Diagnostic] = []
    selected_elsewhere: list[tuple[Path, ActiveWork]] = []
    for candidate in worktrees:
        if same_path(candidate, root):
            continue
        pending, candidate_diagnostics = _session_work(WorkStore(candidate), session)
        unreadable_elsewhere.extend(candidate_diagnostics)
        if pending is None:
            continue
        _check_runtime(session, pending, lookup)
        selected_elsewhere.append((candidate, pending))
        if pending.relocation is None:
            continue
        intended = Path(pending.relocation.target_worktree)
        if not same_path(intended, root):
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
    if previous is not None:
        _check_runtime(session, previous, lookup)
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
    branch = Git(root, timeout=2).maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    replacement = ActiveWork(
        session_key=previous.session_key if previous else session.session_key,
        harness=session.harness,
        session_label=session.session_label,
        session_process=session.session_process,
        issue_id=issue.id,
        issue_reference=issue.reference,
        binding_provenance="explicit-reference",
        started_at=utc_now(),
        working_directory=str(current),
        branch=branch,
        session_id=session.session_id,
    )
    if previous is None:
        store.start(replacement)
    elif not store.replace_current(previous, replacement):
        raise RuntimeError(
            "this Agent Run changed before replacement; nothing was overwritten"
        )
    # The hooks place the session here, so a run recorded at another Worktree
    # of the Repository is where it used to be, and nobody is left behind
    # there.
    elsewhere: list[tuple[Path, ActiveWork]] = []
    for candidate, expected in selected_elsewhere:
        if not WorkStore(candidate).stop_current(expected):
            raise RuntimeError(
                f"this session's earlier Agent Run at {candidate} changed; "
                "it was not removed. Inspect 'dashpot work show' at both Worktrees"
            )
        elsewhere.append((candidate, expected))
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
    if not any(same_path(target_root, worktree) for worktree in worktrees):
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
    if location is None or not same_path(location.worktree, root):
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
    _check_runtime(session, work, lookup)
    if not same_path(worktree, root):
        raise RuntimeError(
            f"this Agent Session's active Agent Run is at {worktree}, not {root}; "
            "nothing was written"
        )
    branch = Git(root, timeout=2).maybe("symbolic-ref", "--quiet", "--short", "HEAD")
    if same_path(root, target_root):
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
                target_worktree=str(target_root), requested_at=utc_now()
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
        stopped, diagnostics = _stop_elsewhere(session, worktrees, None, lookup)
        # Unreadable records are surfaced beside the outcome: this session's
        # run may be among the records that could not be read.
        warnings = [diagnostic.message for diagnostic in diagnostics]
        if not stopped:
            return ["no active Issue work for this session", *warnings]
        return [
            f"stopped work on {work.issue_reference}"
            + ("" if same_path(worktree, root) else f" at {worktree}")
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
    if not store.stop_current(previous):
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
        return session_liveness(work.session_process.key, lookup).liveness != "gone"
    if work.session_id is None:
        return False
    try:
        location = locate_agent_session(
            reachable_hook_stores(repository_worktrees(root)),
            lookup,
            harness=work.harness,
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
            harness=session.harness,
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
    session: AgentSessionIdentity,
    worktrees: Sequence[Path],
    here: Path | None,
    lookup: ProcessLookup,
) -> tuple[list[tuple[Path, ActiveWork]], list[Diagnostic]]:
    """End the session's active runs at every Worktree other than ``here``.

    Each Worktree's unreadable Work Store records come back beside the runs:
    a corrupt record could hide the very run this session is looking for.
    """
    selected: list[tuple[Path, WorkStore, ActiveWork]] = []
    diagnostics: list[Diagnostic] = []
    for worktree in worktrees:
        if here is not None and same_path(worktree, here):
            continue
        store = WorkStore(worktree)
        work, store_diagnostics = _session_work(store, session)
        diagnostics.extend(store_diagnostics)
        if work is not None:
            _check_runtime(session, work, lookup)
            selected.append((worktree, store, work))
    if selected and diagnostics:
        raise DashpotError(
            "unreadable Work Store records prevent safe ownership selection; nothing was removed"
        )
    stopped: list[tuple[Path, ActiveWork]] = []
    for worktree, store, work in selected:
        if not store.stop_current(work):
            raise RuntimeError(
                "this Agent Run changed before stopping; the changed run was not removed"
            )
        stopped.append((worktree, work))
    return stopped, diagnostics


def _check_runtime(
    session: AgentSessionIdentity, work: ActiveWork, lookup: ProcessLookup
) -> None:
    """Refuse reassignment while another runtime may still own the run."""
    recorded = work.session_process.key if work.session_process else None
    if recorded != session.process_key and (
        recorded is None or session_liveness(recorded, lookup).liveness != "gone"
    ):
        raise RuntimeError(
            "this Agent Session has an Agent Run owned by another live or "
            "unobservable runtime; nothing was changed"
        )


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
    """Select one named run while refusing unresolved legacy ownership."""
    active, diagnostics = store.active()
    identity = SessionEvidence(session.harness, session.session_id, session.process_key)
    matches: list[ActiveWork] = []
    for work in active:
        relation = identity.match(work.evidence)
        if relation == "unresolved":
            raise RuntimeError(
                f"ownership of legacy Agent Run {work.session_key} at {store.directory} "
                "is unresolved; nothing was changed. After its recorded process is "
                f"proved gone, run 'dashpot work stop --session {work.session_key}' "
                "at that Worktree, then declare Issue work again"
            )
        if relation == "same":
            matches.append(work)
        elif work.session_key == session.session_key:
            raise RuntimeError("the destination is occupied by a conflicting identity")
    if len(matches) > 1:
        raise RuntimeError(
            "conflicting Agent Runs for this Agent Session; inspect 'dashpot work show' "
            "and end the exact obsolete run with 'dashpot work stop --session'"
        )
    return next(iter(matches), None), diagnostics
