"""Prepare an Issue Worktree, and report whether a Worktree is removable.

Creation is the one Git mutation a management command performs under
[ADR 0008](../../docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md):
one linked Worktree at one path outside every existing Worktree of the
Project, on one new Branch, from a base commit that is never fetched. Every
rule that decides the path, Branch, base, and refusals runs before Git is
called, so ``--dry-run`` reports exactly what creation would do.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .agents import (
    ProcessLookup,
    host_process_lookup,
    reachable_hook_stores,
    session_liveness,
    sessions_at_worktree,
)
from .git import Git, GitError
from .harnesses import HARNESS_DISPLAY
from .issue_profile import IssueProfile
from .issue_resolution import resolve_issue
from .project_config import (
    PROJECT_CONFIG_NAME,
    ProjectConfig,
    load_project_config,
    parse_project_config,
)
from .repository import (
    DEFAULT_BRANCHES,
    LockHolderProbe,
    choose_integration_ref,
    is_within,
    lock_holder,
    worktree_root,
)
from .settings import WORKTREE_ROOT_VARIABLE, Settings, load_settings
from .work_store import WorkStore

WorktreeRootSource = Literal[
    "--worktree-root", "DASHPOT_WORKTREE_ROOT", "settings", "default-sibling"
]
BaseSource = Literal["--base", "origin/HEAD", "local-branch"]
WORKTREE_ROOT_SUFFIX = ".worktrees"
# GitHub's own Issue-branch slug: lower-case words joined by single hyphens,
# kept short enough to read in a Branch listing.
SLUG_LIMIT = 48
INITIALIZING_LOCK = "initializing"


@dataclass(frozen=True, slots=True)
class WorktreePlan:
    """What ``dashpot worktree create`` would do, or did, for one Issue.

    ``refusals`` lists every reason creation is refused; when it is empty and
    ``dry_run`` is false, ``created`` says the Worktree exists at ``path``.
    ``hints`` names existing Worktrees whose Branch looks like this Issue's;
    they are Issue Hints, never an Issue Binding.
    """

    issue_id: str
    issue_reference: str
    path: str
    branch: str
    base_ref: str | None
    base_source: BaseSource | None
    base_commit: str | None
    worktree_root: str
    worktree_root_source: WorktreeRootSource
    dry_run: bool
    created: bool = False
    refusals: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RemovalObstacle:
    """One reason a Worktree is not removable, with the command that acts on it."""

    kind: Literal[
        "main-worktree",
        "dirty",
        "locked",
        "agent-session",
        "agent-run",
        "work-store",
        "unpushed",
        "unmerged",
    ]
    detail: str
    command: str | None = None


@dataclass(frozen=True, slots=True)
class WorktreeRemovability:
    """A read-only report of whether a Worktree can be removed, and why not."""

    path: str
    branch: str | None
    head: str
    role: Literal["main", "linked"]
    removable: bool
    obstacles: tuple[RemovalObstacle, ...] = ()
    remove_commands: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _BaseResolution:
    """The chosen base ref, the rule that chose it, its commit, and any refusals."""

    ref: str | None
    source: BaseSource | None
    commit: str | None
    refusals: tuple[str, ...] = ()


def create_issue_worktree(
    current: Path,
    hint: str,
    *,
    base: str | None = None,
    branch: str | None = None,
    worktree_root_option: Path | None = None,
    dry_run: bool = False,
    timeout: float = 10,
    environ: Mapping[str, str] | None = None,
    settings: Settings | None = None,
    git: Git | None = None,
) -> WorktreePlan:
    """Create a linked Worktree for an Issue, or report why it is refused.

    The Repository Anchor is the checkout the command runs in. Every rule is
    applied before Git mutates anything; a plan with refusals creates
    nothing. With ``dry_run`` the plan is reported and Git is not called.
    """
    anchor = worktree_root(current, git)
    git = (git if git is not None else Git(anchor, timeout)).at(anchor)
    config = load_project_config(anchor)
    issue = resolve_issue(anchor, hint, timeout)
    environment = environ if environ is not None else os.environ
    machine = settings if settings is not None else load_settings()
    refusals: list[str] = []
    hints: list[str] = []
    records = git.worktree_records()
    worktrees = [
        Path(record["worktree"]).resolve()
        for record in records
        if record.get("worktree") and "bare" not in record
    ]

    root, root_source = resolve_worktree_root(
        anchor, worktree_root_option, environment, machine
    )
    refusals.extend(_check_worktree_root(root, worktrees))

    branch_name = branch if branch is not None else default_branch_name(issue)
    refusals.extend(_check_branch_name(git, branch_name))
    path = root / branch_name.replace("/", "-")

    resolution = _resolve_base(git, base)
    refusals.extend(resolution.refusals)
    if resolution.commit is not None:
        refusals.extend(
            _check_base_compatibility(
                git, config, resolution.ref or resolution.commit, resolution.commit
            )
        )

    refusals.extend(_check_collisions(git, records, path, branch_name))
    if branch is None:
        matches = _existing_issue_worktree_matches(issue, branch_name, records)
        hints.extend(f"{match_path} (Branch {name})" for match_path, name in matches)
        refusals.extend(_check_existing_issue_worktrees(str(issue.number), matches))

    plan = WorktreePlan(
        issue_id=issue.id,
        issue_reference=issue.reference,
        path=str(path),
        branch=branch_name,
        base_ref=resolution.ref,
        base_source=resolution.source,
        base_commit=resolution.commit,
        worktree_root=str(root),
        worktree_root_source=root_source,
        dry_run=dry_run,
        refusals=tuple(refusals),
        hints=tuple(hints),
    )
    if dry_run or plan.refusals or resolution.commit is None:
        return plan
    _add_worktree(git, plan)
    return WorktreePlan(
        issue_id=plan.issue_id,
        issue_reference=plan.issue_reference,
        path=plan.path,
        branch=plan.branch,
        base_ref=plan.base_ref,
        base_source=plan.base_source,
        base_commit=plan.base_commit,
        worktree_root=plan.worktree_root,
        worktree_root_source=plan.worktree_root_source,
        dry_run=False,
        created=True,
    )


def resolve_worktree_root(
    anchor: Path,
    option: Path | None,
    environment: Mapping[str, str],
    settings: Settings,
) -> tuple[Path, WorktreeRootSource]:
    """The directory new Worktrees go under, and which source chose it.

    Precedence is ``--worktree-root``, then ``DASHPOT_WORKTREE_ROOT``, then
    the machine-local ``worktreeRoot`` setting, then the sibling directory
    ``<anchor parent>/<anchor name>.worktrees``. The result is the real path.
    """
    if option is not None:
        return option.expanduser().resolve(), "--worktree-root"
    variable = environment.get(WORKTREE_ROOT_VARIABLE)
    if variable:
        return Path(variable).expanduser().resolve(), "DASHPOT_WORKTREE_ROOT"
    if settings.worktree_root is not None:
        return settings.worktree_root.resolve(), "settings"
    sibling = anchor.parent / f"{anchor.name}{WORKTREE_ROOT_SUFFIX}"
    return sibling.resolve(), "default-sibling"


def default_branch_name(issue: IssueProfile) -> str:
    """GitHub's Issue-branch convention, ``<number>-<title-slug>``; a slug for a Local Issue."""
    if issue.origin.kind == "markdown":
        return issue.reference
    slug = title_slug(issue.title)
    number = issue.number
    return f"{number}-{slug}" if slug else str(number)


def title_slug(title: str) -> str:
    """Lower-case words joined by hyphens, cut at a word boundary."""
    words: list[str] = [word for word in re.split(r"[^a-z0-9]+", title.lower()) if word]
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > SLUG_LIMIT:
            break
        slug = candidate
    return slug or (words[0][:SLUG_LIMIT] if words else "")


def _check_worktree_root(root: Path, worktrees: Sequence[Path]) -> list[str]:
    """Refuse a Worktree root that lies inside a Worktree of the Project."""
    for existing in worktrees:
        if is_within(root, existing):
            return [
                f"Worktree root {root} is inside the Worktree {existing}; a new "
                f"Worktree is created outside every Worktree of the Project "
                f"(choose another --worktree-root or {WORKTREE_ROOT_VARIABLE})"
            ]
    return []


def _check_branch_name(git: Git, branch: str) -> list[str]:
    """Refuse a Branch name Git cannot create beside the existing Branches."""
    if git.maybe("check-ref-format", "--branch", branch) is None:
        return [f"{branch!r} is not a valid Branch name"]
    refusals: list[str] = []
    for existing in _local_branches(git):
        if branch.startswith(f"{existing}/"):
            refusals.append(
                f"Branch name {branch} extends the existing Branch {existing} "
                f"with '/', which Git cannot create; choose another --branch"
            )
        elif existing.startswith(f"{branch}/"):
            refusals.append(
                f"Branch name {branch} is a prefix of the existing Branch "
                f"{existing}, which Git cannot create beside it; choose another "
                f"--branch"
            )
    return refusals


def _local_branches(git: Git) -> list[str]:
    records = git.records("refs/heads", fields=("%(refname:short)",))
    return [record[0] for record in records if record[0]]


def _resolve_base(git: Git, option: str | None) -> _BaseResolution:
    """The base ref, which rule chose it, and its exact commit; never fetched."""
    if option is not None:
        commit = _commit_of(git, option)
        if commit is None:
            return _BaseResolution(
                option,
                "--base",
                None,
                (f"--base {option} does not name a commit in this Repository",),
            )
        ref = git.maybe("rev-parse", "--symbolic-full-name", option) or option
        return _BaseResolution(ref, "--base", commit)
    origin_head = git.maybe("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    origin_head = origin_head or None
    origin_commit = _commit_of(git, origin_head) if origin_head is not None else None
    origin_refs = (
        [origin_head] if origin_head is not None and origin_commit is not None else []
    )
    ref = choose_integration_ref(origin_head, origin_refs)
    if ref is not None:
        return _BaseResolution(ref, "origin/HEAD", origin_commit)
    # Each candidate ref is resolved exactly once; the chosen ref's commit is
    # reused rather than resolved again.
    commits = {
        f"refs/heads/{name}": commit
        for name in DEFAULT_BRANCHES
        if (commit := _commit_of(git, f"refs/heads/{name}")) is not None
    }
    candidates = list(commits)
    ref = choose_integration_ref(None, candidates)
    if ref is not None:
        return _BaseResolution(ref, "local-branch", commits[ref])
    local = [
        name.removeprefix("refs/heads/")
        for name in candidates
        if name.startswith("refs/heads/")
    ]
    return _BaseResolution(
        None,
        None,
        None,
        (
            "no base Branch could be chosen: origin/HEAD is not set and there is "
            + ("no" if not local else "more than one")
            + " local main or master Branch; pass --base REF",
        ),
    )


def _commit_of(git: Git, ref: str) -> str | None:
    commit = git.maybe(
        "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"
    )
    return commit or None


def _check_base_compatibility(
    git: Git,
    config: ProjectConfig,
    base_ref: str,
    base_commit: str,
) -> list[str]:
    """The base revision must carry the anchor's Project and Repository Identity."""
    shown = git.run("show", f"{base_commit}:{PROJECT_CONFIG_NAME}")
    if shown.returncode != 0:
        return [
            f"base {base_ref} ({base_commit[:12]}) has no {PROJECT_CONFIG_NAME}; "
            f"a session there could be observed but never opt into Issue work; "
            f"choose a --base that carries the Project configuration"
        ]
    try:
        base_config = parse_project_config(
            shown.stdout, Path(f"{base_ref}:{PROJECT_CONFIG_NAME}")
        )
    except RuntimeError as exc:
        return [f"base {base_ref} ({base_commit[:12]}): {exc}"]
    mismatches = [
        f"{label} {theirs} (the Repository Anchor has {ours})"
        for label, theirs, ours in (
            ("projectId", base_config.project_id, config.project_id),
            ("repositoryId", base_config.repository_id, config.repository_id),
        )
        if theirs != ours
    ]
    if mismatches:
        return [
            f"base {base_ref} ({base_commit[:12]}) carries "
            + " and ".join(mismatches)
            + "; it configures a different Project"
        ]
    return []


def _check_collisions(
    git: Git,
    records: list[dict[str, str]],
    path: Path,
    branch: str,
) -> list[str]:
    """Refuse a path or Branch something already occupies."""
    refusals: list[str] = []
    registered = _registered_at(records, path)
    if registered is not None:
        lock = registered.get("locked")
        if lock is not None and INITIALIZING_LOCK in lock:
            refusals.append(
                f"{path} is a partially created Worktree (locked: {lock}); "
                f"recover with 'git worktree remove -f -f {path}' and "
                f"'git branch -D {_short_branch(registered) or branch}'"
            )
        else:
            refusals.append(
                f"{path} is already a Worktree"
                + (
                    f" on Branch {_short_branch(registered)}"
                    if _short_branch(registered)
                    else ""
                )
            )
    elif path.is_symlink() or path.is_file():
        refusals.append(f"{path} exists and is not a directory")
    elif path.is_dir():
        if any(path.iterdir()):
            refusals.append(f"{path} exists and is not empty")
        else:
            refusals.append(
                f"{path} is an empty directory Dashpot did not create; remove it "
                f"or choose another --branch"
            )
    if _commit_of(git, f"refs/heads/{branch}") is not None:
        checked_out = next(
            (
                record["worktree"]
                for record in records
                if record.get("branch") == f"refs/heads/{branch}"
            ),
            None,
        )
        refusals.append(
            f"Branch {branch} already exists"
            + (f" and is checked out at {checked_out}" if checked_out else "")
            + "; pass --branch NAME for a separate approach"
        )
    return refusals


def _existing_issue_worktree_matches(
    issue: IssueProfile,
    default_branch: str,
    records: list[dict[str, str]],
) -> list[tuple[str, str]]:
    """Worktrees whose Branch looks like this Issue's, as (path, Branch) pairs."""
    number = str(issue.number)
    return [
        (record["worktree"], name)
        for record in records
        if (name := _short_branch(record)) is not None
        and (name in (default_branch, number) or name.startswith(f"{number}-"))
    ]


def _check_existing_issue_worktrees(
    number: str, matches: Sequence[tuple[str, str]]
) -> list[str]:
    """Refuse the default name when a Worktree already looks like this Issue's."""
    if not matches:
        return []
    return [
        f"a Worktree whose Branch looks like Issue #{number}'s already exists: "
        + ", ".join(f"{path} on {name}" for path, name in matches)
        + "; that is a hint, not Issue work — reuse it, or pass --branch NAME "
        "for a separate approach"
    ]


def _registered_at(records: list[dict[str, str]], path: Path) -> dict[str, str] | None:
    for record in records:
        raw = record.get("worktree")
        if raw and Path(raw).resolve() == path:
            return record
    return None


def _short_branch(record: Mapping[str, str]) -> str | None:
    branch = record.get("branch")
    if not branch:
        return None
    return branch.removeprefix("refs/heads/")


def _add_worktree(git: Git, plan: WorktreePlan) -> None:
    """Run the one mutation, verify it, and roll back only what it created."""
    path = Path(plan.path)
    if plan.base_commit is None:
        # A plan with refusals never reaches here; a plan without a resolved
        # base is a programming error, and one -O must not silence.
        raise RuntimeError("worktree plan has no base commit to create from")
    created_directories = _make_directories(path.parent)
    result = git.run("worktree", "add", "-b", plan.branch, str(path), plan.base_commit)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        leftovers = _roll_back(git, plan, created_directories)
        raise RuntimeError(
            f"git worktree add failed: {detail}"
            + "".join(f"; {item}" for item in leftovers)
        )
    problems = _verify_worktree(git, plan)
    if problems:
        raise RuntimeError(
            f"created {path} but it is not the Worktree that was planned: "
            + "; ".join(problems)
            + f"; inspect it with 'git worktree list' and remove it with "
            f"'git worktree remove -f -f {path}' and 'git branch -D {plan.branch}' "
            f"if it is not wanted"
        )


def _make_directories(directory: Path) -> list[Path]:
    """Create the missing ancestors of the Worktree path, innermost last."""
    missing: list[Path] = []
    candidate = directory
    while not candidate.exists():
        missing.append(candidate)
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"cannot create the Worktree root {directory}: {exc}; choose another "
            f"--worktree-root or {WORKTREE_ROOT_VARIABLE}"
        ) from exc
    return list(reversed(missing))


def _roll_back(
    git: Git, plan: WorktreePlan, created_directories: list[Path]
) -> list[str]:
    """Remove only this invocation's Branch and empty directories; report the rest."""
    path = Path(plan.path)
    messages: list[str] = []
    records = git.worktree_records()
    registered = _registered_at(records, path)
    if registered is not None:
        lock = registered.get("locked")
        if lock is not None and INITIALIZING_LOCK in lock:
            messages.append(
                f"a Worktree is registered at {path} locked '{lock}': another "
                f"creator may still be adding it, or a killed add left it behind; "
                f"if it stays locked, recover with 'git worktree remove -f -f "
                f"{path}' and 'git branch -D {plan.branch}'"
            )
        else:
            messages.append(
                f"a Worktree already exists at {path}"
                + (
                    f" on Branch {_short_branch(registered)}"
                    if _short_branch(registered)
                    else ""
                )
                + " and was left alone"
            )
        return messages
    branch_commit = _commit_of(git, f"refs/heads/{plan.branch}")
    if branch_commit is not None:
        checked_out = any(
            record.get("branch") == f"refs/heads/{plan.branch}" for record in records
        )
        if branch_commit == plan.base_commit and not checked_out:
            deleted = git.run("branch", "-D", plan.branch)
            if deleted.returncode == 0:
                messages.append(
                    f"removed the Branch {plan.branch} this command created"
                )
            else:
                messages.append(
                    f"Branch {plan.branch} was created but could not be removed: "
                    f"{deleted.stderr.strip()}; run 'git branch -D {plan.branch}'"
                )
        else:
            messages.append(
                f"Branch {plan.branch} exists and was left alone: it is "
                + ("checked out elsewhere" if checked_out else "not at the base commit")
            )
    if path.is_dir():
        if any(path.iterdir()):
            messages.append(f"{path} is populated and was left alone")
        else:
            with contextlib.suppress(OSError):
                path.rmdir()
    for directory in reversed(created_directories):
        with contextlib.suppress(OSError):
            directory.rmdir()
    return messages


def _verify_worktree(git: Git, plan: WorktreePlan) -> list[str]:
    path = Path(plan.path)
    scoped = git.at(path)
    problems: list[str] = []
    try:
        top = Path(scoped.text("rev-parse", "--show-toplevel")).resolve()
        head = scoped.text("rev-parse", "HEAD")
        branch = scoped.text("symbolic-ref", "--quiet", "--short", "HEAD")
        status = scoped.text("status", "--porcelain=v1")
    except GitError as exc:
        return [str(exc)]
    if top != path:
        problems.append(f"its Worktree root is {top}")
    if head != plan.base_commit:
        problems.append(f"HEAD is {head}, not the base commit")
    if branch != plan.branch:
        problems.append(f"it is on Branch {branch}")
    if status:
        problems.append("it is not clean")
    registered = _registered_at(git.worktree_records(), path)
    if registered is None:
        problems.append("Git does not list it as a Worktree")
    elif "locked" in registered:
        problems.append(f"it is locked: {registered['locked'] or 'no reason reported'}")
    return problems


def describe_worktree_plan(plan: WorktreePlan) -> list[str]:
    """Render a plan or creation result as lines for a person."""
    verb = (
        "would create" if plan.dry_run else ("created" if plan.created else "refused")
    )
    lines = [
        f"{verb} Worktree {plan.path} for {plan.issue_reference} ({plan.issue_id})",
        f"branch: {plan.branch}",
    ]
    if plan.base_commit is not None:
        lines.append(
            f"base: {plan.base_ref} at {plan.base_commit} (from {plan.base_source})"
        )
    lines.append(
        f"worktree root: {plan.worktree_root} (from {plan.worktree_root_source})"
    )
    lines.extend(f"existing Worktree hint: {item}" for item in plan.hints)
    lines.extend(f"refused: {item}" for item in plan.refusals)
    return lines


def check_worktree(
    current: Path,
    target: Path,
    *,
    lookup: ProcessLookup = host_process_lookup,
    lock_probe: LockHolderProbe | None = None,
    timeout: float = 10,
) -> WorktreeRemovability:
    """Report whether a Worktree could be removed, and each reason it cannot.

    Everything here is observed: Git's dirty state and locks, the Agent
    Sessions whose hooks place them at the Worktree, the Agent Runs recorded
    there, and commits its Branch has that no upstream or base Branch has.
    Dashpot removes nothing; each obstacle names the command that acts on it.
    """
    path = target.expanduser().resolve()
    try:
        anchor = worktree_root(current)
    except RuntimeError:
        anchor = worktree_root(path)
    git = Git(anchor, timeout)
    records = git.worktree_records()
    registered = _registered_at(records, path)
    if registered is None:
        raise RuntimeError(f"{path} is not a Worktree of the Repository at {anchor}")
    role: Literal["main", "linked"] = (
        "main" if records and records[0] is registered else "linked"
    )
    branch = _short_branch(registered)
    obstacles: list[RemovalObstacle] = []
    if role == "main":
        obstacles.append(
            RemovalObstacle(
                "main-worktree",
                "the main Worktree cannot be removed with git worktree remove",
            )
        )
    lock = registered.get("locked")
    if lock is not None:
        reason = lock or "no reason reported"
        holder = lock_holder(reason, lock_probe)
        if INITIALIZING_LOCK in reason:
            command = f"git worktree remove -f -f {path}"
        else:
            command = f"git worktree unlock {path}"
        obstacles.append(
            RemovalObstacle(
                "locked", f"locked: {reason} (holding process {holder})", command
            )
        )
    if path.is_dir():
        status = git.at(path).run(
            "status", "--porcelain=v1", "--untracked-files=normal"
        )
        if status.returncode != 0:
            obstacles.append(
                RemovalObstacle(
                    "dirty",
                    f"cannot inspect: {status.stderr.strip() or 'git status failed'}",
                    f"git -C {path} status",
                )
            )
        elif status.stdout:
            count = len(status.stdout.splitlines())
            obstacles.append(
                RemovalObstacle(
                    "dirty",
                    f"{count} changed or untracked path(s); inspect with "
                    f"'git -C {path} status'",
                    f"git worktree remove --force {path}",
                )
            )
    worktrees = [
        Path(record["worktree"]).resolve()
        for record in records
        if record.get("worktree") and "bare" not in record
    ]
    stores = reachable_hook_stores(worktrees)
    for location in sessions_at_worktree(path, stores, lookup):
        record = location.record
        obstacles.append(
            RemovalObstacle(
                "agent-session",
                f"{HARNESS_DISPLAY[record.harness]} session {record.session_id} is "
                f"{record.outcome} here (last activity {record.last_activity_at})",
            )
        )
    active, work_diagnostics = WorkStore(path).active()
    # A record that cannot be read may still be a live Agent Run; removable
    # is never claimed on evidence that could not be examined.
    obstacles.extend(
        RemovalObstacle("work-store", diagnostic.message)
        for diagnostic in work_diagnostics
    )
    for work in active:
        liveness = (
            session_liveness(work.session_process.as_record(), lookup).liveness
            if work.session_process is not None
            else "unknown"
        )
        if liveness == "gone":
            detail = (
                f"Orphaned Agent Run on {work.issue_reference} for {work.session_label}"
            )
            command = f"cd {path} && dashpot work stop --session {work.session_key}"
        else:
            detail = (
                f"{work.session_label} is working on {work.issue_reference} "
                f"(session {liveness})"
            )
            command = "dashpot work stop (inside that session)"
        obstacles.append(RemovalObstacle("agent-run", detail, command))
    if branch is not None:
        obstacles.extend(_branch_obstacles(git, path, branch))
    remove_commands: tuple[str, ...] = ()
    if role == "linked":
        remove_commands = (f"git worktree remove {path}",) + (
            (f"git branch -d {branch}",) if branch else ()
        )
    return WorktreeRemovability(
        path=str(path),
        branch=branch,
        head=registered.get("HEAD", ""),
        role=role,
        removable=not obstacles,
        obstacles=tuple(obstacles),
        remove_commands=remove_commands,
    )


def _branch_obstacles(git: Git, path: Path, branch: str) -> list[RemovalObstacle]:
    obstacles: list[RemovalObstacle] = []
    upstream = git.maybe(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"
    )
    # The Integration Branch is chosen by the same rule as a new Worktree's
    # base; when none can be, integration is unknown rather than complete.
    resolution = _resolve_base(git, None)
    base_ref, base_commit = resolution.ref, resolution.commit
    unmerged = (
        _count(git, f"{base_commit}..refs/heads/{branch}") if base_commit else None
    )
    if unmerged is None:
        reason = (
            "; ".join(resolution.refusals)
            if resolution.refusals
            else f"commits not reachable from {base_ref} could not be counted"
        )
        obstacles.append(
            RemovalObstacle(
                "unmerged",
                f"cannot tell whether Branch {branch} is integrated: {reason}",
                f"git log --oneline {branch}",
            )
        )
    if upstream:
        ahead = _count(git, f"{upstream}..refs/heads/{branch}")
        if ahead:
            obstacles.append(
                RemovalObstacle(
                    "unpushed",
                    f"{ahead} commit(s) not on {upstream}",
                    f"git -C {path} push",
                )
            )
    elif unmerged:
        obstacles.append(
            RemovalObstacle(
                "unpushed",
                f"Branch {branch} has no upstream and {unmerged} commit(s) of its own",
                f"git -C {path} push -u origin {branch}",
            )
        )
    if unmerged:
        obstacles.append(
            RemovalObstacle(
                "unmerged",
                f"{unmerged} commit(s) not reachable from {base_ref}",
                f"git log --oneline {base_ref}..{branch}",
            )
        )
    return obstacles


def _count(git: Git, revision_range: str) -> int | None:
    return git.count("rev-list", "--count", revision_range)


def describe_removability(report: WorktreeRemovability) -> list[str]:
    """Render a removability report as lines for a person."""
    label = f"{report.path}" + (f" (Branch {report.branch})" if report.branch else "")
    if report.removable:
        lines = [f"{label} is removable"]
        lines.extend(f"remove with: {command}" for command in report.remove_commands)
        return lines
    lines = [f"{label} is not removable:"]
    for obstacle in report.obstacles:
        line = f"- {obstacle.kind}: {obstacle.detail}"
        if obstacle.command:
            line += f" -> {obstacle.command}"
        lines.append(line)
    return lines
