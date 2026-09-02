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

from .git import Git, GitError
from .harnesses import HARNESS_DISPLAY
from .hook_records import reachable_hook_stores, sessions_at_worktree
from .issue_profile import IssueProfile
from .issue_resolution import resolve_issue
from .liveness import session_liveness
from .models import LaxSequence, PublishedModel
from .processes import ProcessLookup, host_process_lookup
from .project_config import (
    PROJECT_CONFIG_NAME,
    ProjectConfig,
    load_project_config,
    parse_project_config,
)
from .repository import (
    DEFAULT_BRANCHES,
    LockHolderProbe,
    assess_content_integration,
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


class WorktreePlan(PublishedModel):
    """What ``dashpot worktree create`` would do, or did, for one Issue.

    ``refusals`` lists every reason creation is refused; when it is empty and
    ``dry_run`` is false, ``created`` says the Worktree exists at ``path``.
    ``hints`` names existing Worktrees whose Branch looks like this Issue's;
    they are Issue Hints, never an Issue Binding. ``warnings`` carries
    non-fatal observations, such as unknown machine settings fields.
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
    refusals: LaxSequence[str] = ()
    hints: LaxSequence[str] = ()
    warnings: LaxSequence[str] = ()


class RemovalObstacle(PublishedModel):
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
        "detached",
    ]
    detail: str
    command: str | None = None


class WorktreeRemovability(PublishedModel):
    """A read-only report of whether a Worktree can be removed, and why not."""

    path: str
    branch: str | None
    head: str
    role: Literal["main", "linked"]
    removable: bool
    obstacles: LaxSequence[RemovalObstacle] = ()
    remove_commands: LaxSequence[str] = ()


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
    # Machine-settings diagnostics ride the plan so both the text and the
    # JSON renderings surface them without a channel of their own.
    warnings = tuple(diagnostic.message for diagnostic in machine.diagnostics)
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
        warnings=warnings,
    )
    if dry_run or plan.refusals or resolution.commit is None:
        return plan
    _add_worktree(git, plan)
    # Hints named other Worktrees that looked like this Issue's; once this one
    # exists they have served their purpose and are not restated.
    return plan.model_copy(update={"dry_run": False, "created": True, "hints": ()})


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
    lines.extend(f"warning: {item}" for item in plan.warnings)
    # Refusals are the CLI's to render from the structured ``plan.refusals``:
    # they are error-contract lines for stderr, not part of this report.
    return lines


def linked_worktrees(current: Path, *, timeout: float = 10) -> list[Path]:
    """List the linked Worktrees of the Repository ``current`` belongs to.

    The main Worktree is never removable, so a check of every Worktree is a
    check of the linked ones; a bare entry is not a Worktree.
    """
    anchor = worktree_root(current)
    records = Git(anchor, timeout).worktree_records()
    return sorted(
        Path(record["worktree"]).resolve()
        for record in records[1:]
        if record.get("worktree") and "bare" not in record
    )


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
    located = locate_worktree(current, target, timeout=timeout)
    git, path = located.git, located.path
    branch = located.branch
    obstacles = assess_worktree_safety(located, lock_probe)
    obstacles.extend(assess_worktree_occupancy(path, located.worktrees, lookup))
    content_integrated = False
    if branch is not None:
        branch_obstacles, content_integrated = assess_branch_preservation(
            git, path, branch
        )
        obstacles.extend(branch_obstacles)
    elif located.detached:
        obstacles.extend(assess_detached_head_preservation(git, located.head))
    remove_commands: tuple[str, ...] = ()
    if located.role == "linked":
        # ``branch -d`` refuses a squash-merged Branch, whose commits are not
        # reachable; the forced form is the command that acts on it.
        delete = "-D" if content_integrated else "-d"
        remove_commands = (f"git worktree remove {path}",) + (
            (f"git branch {delete} {branch}",) if branch else ()
        )
    return WorktreeRemovability(
        path=str(path),
        branch=branch,
        head=located.head,
        role=located.role,
        removable=not obstacles,
        obstacles=tuple(obstacles),
        remove_commands=remove_commands,
    )


@dataclass(frozen=True, slots=True)
class LocatedWorktree:
    """One registered Worktree, as Git lists it, with the adapter at its anchor."""

    git: Git
    anchor: Path
    path: Path
    record: Mapping[str, str]
    role: Literal["main", "linked"]
    # Every Worktree of the Repository, resolved; bare entries are not Worktrees.
    worktrees: tuple[Path, ...]

    @property
    def branch(self) -> str | None:
        return _short_branch(self.record)

    @property
    def head(self) -> str:
        return self.record.get("HEAD", "")

    @property
    def detached(self) -> bool:
        return "detached" in self.record


def locate_worktree(
    current: Path, target: Path, *, timeout: float = 10, git: Git | None = None
) -> LocatedWorktree:
    """Find ``target`` among the Worktrees of the Repository ``current`` is in.

    A path Git does not list is a ``RuntimeError``: every assessment is about
    a registered Worktree, never about a directory that merely looks like one.
    """
    path = target.expanduser().resolve()
    try:
        anchor = worktree_root(current, git)
    except RuntimeError:
        anchor = worktree_root(path, git)
    scoped = (git if git is not None else Git(anchor, timeout)).at(anchor)
    records = scoped.worktree_records()
    registered = _registered_at(records, path)
    if registered is None:
        raise RuntimeError(f"{path} is not a Worktree of the Repository at {anchor}")
    role: Literal["main", "linked"] = (
        "main" if records and records[0] is registered else "linked"
    )
    worktrees = tuple(
        Path(record["worktree"]).resolve()
        for record in records
        if record.get("worktree") and "bare" not in record
    )
    return LocatedWorktree(scoped, anchor, path, registered, role, worktrees)


def assess_worktree_safety(
    located: LocatedWorktree, lock_probe: LockHolderProbe | None = None
) -> list[RemovalObstacle]:
    """The obstacles Git itself raises: the main Worktree, a lock, a dirty tree."""
    path, registered = located.path, located.record
    obstacles: list[RemovalObstacle] = []
    if located.role == "main":
        obstacles.append(
            RemovalObstacle(
                kind="main-worktree",
                detail="the main Worktree cannot be removed with git worktree remove",
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
                kind="locked",
                detail=f"locked: {reason} (holding process {holder})",
                command=command,
            )
        )
    if path.is_dir():
        status = located.git.at(path).run(
            "status", "--porcelain=v1", "--untracked-files=normal"
        )
        if status.returncode != 0:
            obstacles.append(
                RemovalObstacle(
                    kind="dirty",
                    detail=f"cannot inspect: "
                    f"{status.stderr.strip() or 'git status failed'}",
                    command=f"git -C {path} status",
                )
            )
        elif status.stdout:
            count = len(status.stdout.splitlines())
            obstacles.append(
                RemovalObstacle(
                    kind="dirty",
                    detail=f"{count} changed or untracked path(s); inspect with "
                    f"'git -C {path} status'",
                    command=f"git worktree remove --force {path}",
                )
            )
    return obstacles


def assess_worktree_occupancy(
    path: Path,
    worktrees: Sequence[Path],
    lookup: ProcessLookup = host_process_lookup,
) -> list[RemovalObstacle]:
    """The Agent Sessions, Agent Runs, and unreadable Work Store records at a Worktree."""
    obstacles: list[RemovalObstacle] = []
    stores = reachable_hook_stores(worktrees)
    for location in sessions_at_worktree(path, stores, lookup):
        record = location.record
        obstacles.append(
            RemovalObstacle(
                kind="agent-session",
                detail=f"{HARNESS_DISPLAY[record.harness]} session "
                f"{record.session_id} is {record.outcome} here "
                f"(last activity {record.last_activity_at})",
            )
        )
    active, work_diagnostics = WorkStore(path).active()
    # A record that cannot be read may still be a live Agent Run; removable
    # is never claimed on evidence that could not be examined.
    obstacles.extend(
        RemovalObstacle(kind="work-store", detail=diagnostic.message)
        for diagnostic in work_diagnostics
    )
    for work in active:
        liveness = (
            session_liveness(work.session_process.key, lookup).liveness
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
        obstacles.append(
            RemovalObstacle(kind="agent-run", detail=detail, command=command)
        )
    return obstacles


def assess_branch_preservation(
    git: Git, path: Path, branch: str
) -> tuple[list[RemovalObstacle], bool]:
    """The Branch's obstacles, and whether its content is already integrated.

    Retained commits whose content the Integration Branch already holds — a
    squash merge — obstruct nothing: neither unmerged nor unpushed, since the
    work is where it was meant to land ([ADR 0017](../../docs/adr/0017-observe-branch-integration-by-content-when-commits-are-unreachable.md)).
    """
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
    content_integrated = False
    if unmerged and base_ref is not None:
        try:
            content_integrated = bool(
                assess_content_integration(
                    git,
                    base_ref,
                    f"refs/heads/{branch}",
                    git.maybe("log", "-1", "--format=%cI", f"refs/heads/{branch}"),
                )
            )
        except GitError:
            content_integrated = False
        if content_integrated:
            unmerged = 0
    if unmerged is None:
        reason = (
            "; ".join(resolution.refusals)
            if resolution.refusals
            else f"commits not reachable from {base_ref} could not be counted"
        )
        obstacles.append(
            RemovalObstacle(
                kind="unmerged",
                detail=f"cannot tell whether Branch {branch} is integrated: {reason}",
                command=f"git log --oneline {branch}",
            )
        )
    if upstream:
        ahead = _count(git, f"{upstream}..refs/heads/{branch}")
        if ahead:
            obstacles.append(
                RemovalObstacle(
                    kind="unpushed",
                    detail=f"{ahead} commit(s) not on {upstream}",
                    command=f"git -C {path} push",
                )
            )
    elif unmerged:
        obstacles.append(
            RemovalObstacle(
                kind="unpushed",
                detail=f"Branch {branch} has no upstream and {unmerged} commit(s) "
                f"of its own",
                command=f"git -C {path} push -u origin {branch}",
            )
        )
    if unmerged:
        obstacles.append(
            RemovalObstacle(
                kind="unmerged",
                detail=f"{unmerged} commit(s) not reachable from {base_ref}",
                command=f"git log --oneline {base_ref}..{branch}",
            )
        )
    return obstacles, content_integrated


def durable_refs_containing(git: Git, commit: str) -> list[str]:
    """Local, Remote-Tracking, and tag refs from which ``commit`` is reachable."""
    records = git.records(
        "--contains",
        commit,
        "refs/heads",
        "refs/remotes",
        "refs/tags",
        fields=("%(refname)",),
    )
    return [record[0] for record in records if record[0]]


def assess_detached_head_preservation(git: Git, head: str) -> list[RemovalObstacle]:
    """A detached HEAD no durable ref reaches is lost with the Worktree."""
    if not head:
        return []
    try:
        if durable_refs_containing(git, head):
            return []
    except GitError as exc:
        detail = f"cannot tell whether commit {head[:7]} is reachable: {exc.detail}"
    else:
        detail = (
            f"detached at {head[:7]}, which no local Branch, Remote-Tracking "
            f"Branch, or tag reaches"
        )
    return [
        RemovalObstacle(
            kind="detached",
            detail=detail,
            command=f"git branch rescue/{head[:7]} {head}",
        )
    ]


def ignored_content(git: Git, path: Path) -> list[str]:
    """The ignored paths in a Worktree, which unforced removal deletes too.

    Directories whose every entry is ignored are reported as one path with a
    trailing slash, as ``git status --ignored`` collapses them.
    """
    if not path.is_dir():
        return []
    listing = git.at(path).maybe(
        "status", "--porcelain=v1", "--ignored=traditional", "-z"
    )
    if listing is None:
        return []
    ignored: list[str] = []
    skip = False
    for entry in listing.split("\0"):
        if skip:
            # A rename or copy entry is followed by its source path as a
            # field of its own.
            skip = False
            continue
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if code[0] in "RC":
            skip = True
        if code == "!!":
            ignored.append(name)
    return ignored


def _count(git: Git, revision_range: str) -> int | None:
    return git.count("rev-list", "--count", revision_range)


def describe_removability(report: WorktreeRemovability) -> list[str]:
    """Render a removability report as lines for a person.

    Field/value lines name the Worktree, its Branch, and the verdict; the
    obstacles and the commands to run are indented beneath them so a block
    scans as one Worktree and the commands stand apart from the facts.
    """
    lines = [
        f"Worktree   {report.path}",
        f"Branch     {report.branch or '(detached)'}",
        f"Removable  {'yes' if report.removable else 'no'}",
    ]
    if report.obstacles:
        lines.append("Obstacles")
        for obstacle in report.obstacles:
            lines.append(f"  - {obstacle.kind}: {obstacle.detail}")
            if obstacle.command:
                lines.append(f"      run: {obstacle.command}")
    if report.removable and report.remove_commands:
        lines.append("Remove with")
        lines.extend(f"  $ {command}" for command in report.remove_commands)
    return lines
