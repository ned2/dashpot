"""Perform confirmed Cleanup targets after rechecking their evidence."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import computed_field

from ...core.commands import non_interactive_runner
from ...core.errors import DashpotError
from ...core.git import Git, GitError, last_stderr_line
from ...core.pydantic import LaxSequence, PublishedModel
from ...sessions.processes import ProcessLookup, host_process_lookup
from ..repository import (
    LOCAL_REF_PREFIX,
    REMOTE_REF_PREFIX,
    LockHolderProbe,
)
from ..worktrees.records import registered_at
from .preview import describe_cleanup_preview, inspect_cleanup
from .targets import (
    CleanupPreview,
    CleanupRequest,
    CleanupTarget,
    TargetKind,
)

Outcome = Literal["deleted", "already-absent", "refused", "unknown"]


CLEANUP_ENVIRONMENT: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}


# Remote first, so a lease refusal can still revise the preview; the Worktree
# before the Branch it has checked out.
_ORDER: Mapping[TargetKind, int] = {
    "remote-branch": 0,
    "worktree": 1,
    "local-branch": 2,
}


CHANGED_SINCE_PREVIEW = (
    "the observed state changed since the preview; confirm again against the "
    "revised preview"
)


class CleanupError(DashpotError, RuntimeError):
    """A Cleanup command refused before previewing: a usage-shaped mistake."""


@dataclass(frozen=True, slots=True)
class CleanupConfirmation:
    """What a person confirmed: the previewed facts and the targets selected.

    ``fingerprint`` is the preview's, ``selected`` names targets by identity,
    and ``delete_ignored`` acknowledges that a Worktree's ignored content goes
    with it.
    """

    request: CleanupRequest
    fingerprint: str
    selected: tuple[str, ...]
    delete_ignored: bool = False


class TargetResult(PublishedModel):
    """What one selected target came to."""

    identity: str
    kind: TargetKind
    label: str
    expected: str
    outcome: Outcome
    detail: str
    # The command that recreates a deleted target while Git still has the commit.
    recovery: str | None = None


class CleanupReport(PublishedModel):
    """What one confirmed Cleanup did, or why it did nothing.

    ``performed`` is false when the observed state changed since the preview
    (``changed``, with the fresh ``preview`` to confirm again), when the
    selection was refused (``refusals``), or on a dry run, which lists the
    targets it would have attempted, in order, as ``planned``.
    """

    kind: Literal["branch", "worktree"]
    subject: str
    anchor: str
    dry_run: bool
    performed: bool
    preview: CleanupPreview
    changed: bool = False
    refusals: LaxSequence[str] = ()
    planned: LaxSequence[str] = ()
    results: LaxSequence[TargetResult] = ()

    @computed_field
    @property
    def succeeded(self) -> bool:
        """Every selected target was deleted or was already absent."""
        return self.performed and all(
            result.outcome in {"deleted", "already-absent"} for result in self.results
        )


def cleanup_git(timeout: float) -> Git:
    """The production adapter for a Cleanup: non-interactive, with Dashpot's timeout."""
    return Git(Path.cwd(), timeout, non_interactive_runner(CLEANUP_ENVIRONMENT))


def perform_cleanup(
    confirmation: CleanupConfirmation,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    protected: Sequence[Path] = (),
    timeout: float = 10,
    git: Git | None = None,
    dry_run: bool = False,
) -> CleanupReport:
    """Perform a confirmed Cleanup after re-inspecting it, or say why not.

    The preview is taken again and compared by fingerprint: anything observed
    differently since the person confirmed means nothing is performed and the
    revised preview is returned for another confirmation. A dry run stops
    after validating the selection. Targets run in order — remote, Worktree,
    local Branch — and after a refused or unknown outcome the rest are
    reported as not attempted rather than tried on changed ground.
    """
    adapter = git if git is not None else cleanup_git(timeout)
    preview = inspect_cleanup(
        confirmation.request,
        lookup=lookup,
        lock_probe=lock_probe,
        protected=protected,
        timeout=timeout,
        git=adapter,
    )
    if preview.fingerprint != confirmation.fingerprint:
        return _report(
            preview, dry_run, changed=True, refusals=(CHANGED_SINCE_PREVIEW,)
        )
    refusals, ordered = _select(preview, confirmation)
    if refusals:
        return _report(preview, dry_run, refusals=tuple(refusals))
    if dry_run:
        return _report(
            preview, dry_run, planned=tuple(target.identity for target in ordered)
        )
    scoped = adapter.at(Path(preview.anchor))
    results: list[TargetResult] = []
    halted: TargetResult | None = None
    for target in ordered:
        if halted is not None:
            results.append(
                _result(
                    target,
                    "refused",
                    f"not attempted: {halted.label} was {halted.outcome}",
                )
            )
            continue
        result = _perform(scoped, target)
        results.append(result)
        if result.outcome in {"refused", "unknown"}:
            halted = result
    return _report(preview, dry_run, performed=True, results=tuple(results))


def _report(
    preview: CleanupPreview,
    dry_run: bool,
    *,
    performed: bool = False,
    changed: bool = False,
    refusals: Sequence[str] = (),
    planned: Sequence[str] = (),
    results: Sequence[TargetResult] = (),
) -> CleanupReport:
    return CleanupReport(
        kind=preview.kind,
        subject=preview.subject,
        anchor=preview.anchor,
        dry_run=dry_run,
        performed=performed,
        preview=preview,
        changed=changed,
        refusals=tuple(refusals),
        planned=tuple(planned),
        results=tuple(results),
    )


def _select(
    preview: CleanupPreview, confirmation: CleanupConfirmation
) -> tuple[list[str], list[CleanupTarget]]:
    """The selected targets in performing order, or every reason to refuse them."""
    refusals = list(preview.refusals)
    if not confirmation.selected:
        refusals.append("no target is selected")
    chosen: list[CleanupTarget] = []
    for identity in confirmation.selected:
        target = preview.target(identity)
        if target is None:
            refusals.append(f"{identity} is not a target of this preview")
            continue
        if not target.available:
            reasons = "; ".join(blocker.detail for blocker in target.blockers)
            refusals.append(f"{target.label} is unavailable: {reasons}")
            continue
        if target.requires is not None and target.requires not in confirmation.selected:
            refusals.append(
                f"{target.label} can only be deleted together with {target.requires}"
            )
            continue
        chosen.append(target)
    if (
        preview.ignored
        and any(target.kind == "worktree" for target in chosen)
        and not confirmation.delete_ignored
    ):
        refusals.append(
            f"removing the Worktree deletes {len(preview.ignored)} ignored path(s) "
            f"inside it, which must be acknowledged"
        )
    chosen.sort(key=lambda target: _ORDER[target.kind])
    return refusals, chosen


def _perform(git: Git, target: CleanupTarget) -> TargetResult:
    if target.kind == "local-branch":
        return _delete_local_branch(git, target)
    if target.kind == "worktree":
        return _remove_worktree(git, target)
    return _delete_remote_branch(git, target)


def _delete_local_branch(git: Git, target: CleanupTarget) -> TargetResult:
    """Delete the ref only if it is still at the previewed commit."""
    refname = target.ref or ""
    name = refname.removeprefix(LOCAL_REF_PREFIX)
    recovery = f"git branch {name} {target.expected}"
    try:
        result = git.run("update-ref", "-d", refname, target.expected)
    except GitError as exc:
        return _result(
            target,
            "unknown",
            f"git update-ref did not complete: {exc.detail}; check with: "
            f"git rev-parse --verify {refname}",
            recovery,
        )
    if result.returncode != 0:
        if not _ref_exists(git, refname):
            return _result(target, "already-absent", f"{refname} was already gone")
        return _result(
            target,
            "refused",
            last_stderr_line(result.stderr) or "git update-ref refused",
        )
    # The Branch's configuration goes with its ref; ``update-ref`` leaves it,
    # and a Branch that had none makes the removal a no-op.
    with contextlib.suppress(GitError):
        git.run("config", "--remove-section", f"branch.{name}")
    return _result(
        target, "deleted", f"deleted {refname} at {target.expected[:7]}", recovery
    )


def _delete_remote_branch(git: Git, target: CleanupTarget) -> TargetResult:
    """Delete at the remote only if it still holds the previewed commit.

    The lease is the Remote-Tracking Branch's tip as of the last fetch. Git
    rejects the push with ``stale info`` both when the remote advanced and
    when the Branch is already gone there, so that rejection is followed by
    one read-only ``ls-remote`` to tell the two apart; nothing is fetched,
    and a stale Remote-Tracking Branch is left for the next Remote Fetch to
    prune. A successful delete push drops the Remote-Tracking Branch itself
    under the canonical mapping the preview required.
    """
    remote = target.remote or ""
    tracking = target.ref or ""
    name = tracking.removeprefix(f"{REMOTE_REF_PREFIX}{remote}/")
    refname = f"{LOCAL_REF_PREFIX}{name}"
    recovery = f"git push {remote} {target.expected}:{refname}"
    try:
        result = git.run(
            "push",
            f"--force-with-lease={refname}:{target.expected}",
            remote,
            f":{refname}",
        )
    except GitError as exc:
        return _result(
            target,
            "unknown",
            f"git push did not complete: {exc.detail}; check with: "
            f"git ls-remote --heads {remote} {refname}; a surviving "
            f"{_prune_hint(remote, tracking)}",
            recovery,
        )
    if result.returncode == 0:
        return _result(
            target,
            "deleted",
            f"deleted {name} at {remote}, which was at {target.expected[:7]}; "
            f"Git dropped {tracking}",
            recovery,
        )
    reason = _push_reason(result.stderr)
    if "stale info" not in result.stderr:
        return _result(target, "refused", reason)
    presence = _remote_ref_presence(git, remote, refname)
    if presence == "absent":
        return _result(
            target,
            "already-absent",
            f"{name} at {remote} was already gone; the stale "
            f"{_prune_hint(remote, tracking)}",
        )
    if presence == "present":
        return _result(
            target,
            "refused",
            f"{remote} no longer has {name} at the leased {target.expected[:7]}: "
            f"it moved since the last fetch; press f (or git fetch --prune "
            f"{remote}), then confirm against the revised preview",
        )
    return _result(target, "refused", reason)


def _prune_hint(remote: str, tracking: str) -> str:
    """How a stale Remote-Tracking Branch goes: the next Remote Fetch, never Cleanup."""
    return (
        f"{tracking} is pruned by the next Remote Fetch: press f, or "
        f"git fetch --prune {remote}"
    )


def _push_reason(stderr: str) -> str:
    """Git's first rejection or fatal line: a push failure ends in advice."""
    for line in stderr.splitlines():
        if line.strip().startswith(("! [", "error:", "fatal:")):
            return line.strip()
    return last_stderr_line(stderr) or "git push refused"


def _remote_ref_presence(
    git: Git, remote: str, refname: str
) -> Literal["present", "absent", "unknown"]:
    """Ask the remote, read-only, whether it still has ``refname``."""
    try:
        result = git.run("ls-remote", "--exit-code", "--heads", remote, refname)
    except GitError:
        return "unknown"
    if result.returncode == 0:
        return "present"
    # ``--exit-code`` makes 2 the answer "no matching ref"; anything else is
    # the remote not answering, which must not be read as absence.
    return "absent" if result.returncode == 2 else "unknown"


def _remove_worktree(git: Git, target: CleanupTarget) -> TargetResult:
    """Remove the Worktree without force, so Git refuses what changed underneath."""
    path = target.path or ""
    recovery = (
        f"git worktree add {path} {target.ref.removeprefix(LOCAL_REF_PREFIX)}"
        if target.ref
        else f"git worktree add --detach {path} {target.expected}"
    )
    try:
        result = git.run("worktree", "remove", "--", path)
    except GitError as exc:
        return _result(
            target,
            "unknown",
            f"git worktree remove did not complete: {exc.detail}; check with: "
            f"git worktree list",
            recovery,
        )
    if result.returncode != 0:
        if not Path(path).exists() and not _registered(git, path):
            return _result(target, "already-absent", f"{path} was already gone")
        return _result(
            target,
            "refused",
            last_stderr_line(result.stderr) or "git worktree remove refused",
        )
    return _result(target, "deleted", f"removed {path}", recovery)


def _ref_exists(git: Git, refname: str) -> bool:
    try:
        return git.maybe("rev-parse", "--verify", "--quiet", refname) is not None
    except GitError:
        # Not knowing is not absence: the target is reported refused, not gone.
        return True


def _registered(git: Git, path: str) -> bool:
    try:
        records = git.worktree_records()
    except GitError:
        return True
    return registered_at(records, Path(path)) is not None


def _result(
    target: CleanupTarget, outcome: Outcome, detail: str, recovery: str | None = None
) -> TargetResult:
    return TargetResult(
        identity=target.identity,
        kind=target.kind,
        label=target.label,
        expected=target.expected,
        outcome=outcome,
        detail=detail,
        recovery=recovery,
    )


def describe_cleanup_report(report: CleanupReport) -> list[str]:
    """Render a report as lines for a person: what happened to each target."""
    verb = "Delete Branch" if report.kind == "branch" else "Remove Worktree"
    lines = [f"{verb:<16}{report.subject}", f"{'Anchor':<16}{report.anchor}"]
    if report.changed:
        lines.append(f"{'Changed':<16}{CHANGED_SINCE_PREVIEW}")
        lines.extend(describe_cleanup_preview(report.preview)[2:])
        return lines
    lines.extend(f"{'Refused':<16}{refusal}" for refusal in report.refusals)
    if report.refusals:
        return lines
    if report.dry_run:
        lines.append(f"{'Dry run':<16}would attempt, in order")
        for index, identity in enumerate(report.planned, 1):
            target = report.preview.target(identity)
            label = target.label if target is not None else identity
            lines.append(f"  {index}. {label} {_where(target)}".rstrip())
        return lines
    lines.append("Results")
    for result in report.results:
        target = report.preview.target(result.identity)
        lines.append(
            f"  {result.outcome:<15}{result.label} {_where(target)} "
            f"@ {result.expected[:7]}"
        )
        lines.append(f"      {result.detail}")
        if result.recovery and result.outcome == "deleted":
            lines.append(f"      recover: {result.recovery}")
    return lines


def _where(target: CleanupTarget | None) -> str:
    if target is None:
        return ""
    if target.kind == "worktree":
        return target.path or ""
    return target.ref or ""
