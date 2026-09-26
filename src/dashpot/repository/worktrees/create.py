"""Prepare an Issue Worktree after validating its plan."""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from ...core.commands import nonzero_exit_fails
from ...core.errors import DashpotError
from ...core.git import Git, GitError
from ...core.issue_profile import IssueProfile
from ...core.pydantic import LaxSequence, PublishedModel
from ...core.worktree_paths import (
    is_within,
    main_worktree,
    worktree_paths,
    worktree_root,
)
from ...issues.issue_resolution import resolve_issue
from ...project.project_config import (
    PROJECT_CONFIG_NAME,
    ProjectConfig,
    ProjectConfigError,
    load_project_config,
    parse_project_config,
)
from ...project.settings import WORKTREE_ROOT_VARIABLE, Settings, load_settings
from .base import BaseSource, commit_of, resolve_base
from .records import (
    INITIALIZING_LOCK,
    registered_at,
    short_branch,
)

WorktreeRootSource = Literal[
    "--worktree-root", "DASHPOT_WORKTREE_ROOT", "settings", "default-sibling"
]


class WorktreeCreateError(DashpotError):
    """A Worktree creation that failed or left something to inspect by hand."""


WORKTREE_ROOT_SUFFIX = ".worktrees"


# GitHub's own Issue-branch slug: lower-case words joined by single hyphens,
# kept short enough to read in a Branch listing.
SLUG_LIMIT = 48


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
    main_worktree: str
    dry_run: bool
    created: bool = False
    refusals: LaxSequence[str] = ()
    hints: LaxSequence[str] = ()
    warnings: LaxSequence[str] = ()


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

    The Repository Anchor is the checkout the command runs in: it supplies the
    Project configuration, the Issue Source, and the base. The default
    Worktree Root is a property of the Git Repository instead, taken from its
    main working tree, so every checkout of one Repository shares one pool.
    Every rule is applied before Git mutates anything; a plan with refusals
    creates nothing. With ``dry_run`` the plan is reported and Git is not
    called.
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
    worktrees = worktree_paths(records)
    main = main_worktree(records)

    root, root_source = resolve_worktree_root(
        main, worktree_root_option, environment, machine
    )
    refusals.extend(_check_worktree_root(root, worktrees))

    branch_name = branch if branch is not None else default_branch_name(issue)
    refusals.extend(_check_branch_name(git, branch_name))
    path = root / branch_name.replace("/", "-")

    resolution = resolve_base(git, base)
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
        main_worktree=str(main),
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
    main_worktree: Path,
    option: Path | None,
    environment: Mapping[str, str],
    settings: Settings,
) -> tuple[Path, WorktreeRootSource]:
    """The directory new Worktrees go under, and which source chose it.

    Precedence is ``--worktree-root``, then ``DASHPOT_WORKTREE_ROOT``, then
    the machine-local ``worktree_root`` setting, then the sibling directory
    ``<main parent>/<main name>.worktrees`` of the Repository's main working
    tree — never of the linked Worktree the command happens to run in, so
    one Repository has one default pool. The result is the real path.
    """
    if option is not None:
        return option.expanduser().resolve(), "--worktree-root"
    variable = environment.get(WORKTREE_ROOT_VARIABLE)
    if variable:
        return Path(variable).expanduser().resolve(), "DASHPOT_WORKTREE_ROOT"
    if settings.worktree_root is not None:
        return settings.worktree_root.resolve(), "settings"
    sibling = main_worktree.parent / f"{main_worktree.name}{WORKTREE_ROOT_SUFFIX}"
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
    except ProjectConfigError as exc:
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
    registered = registered_at(records, path)
    if registered is not None:
        lock = registered.get("locked")
        if lock is not None and INITIALIZING_LOCK in lock:
            refusals.append(
                f"{path} is a partially created Worktree (locked: {lock}); "
                f"recover with 'git worktree remove -f -f {path}' and "
                f"'git branch -D {short_branch(registered) or branch}'"
            )
        else:
            refusals.append(
                f"{path} is already a Worktree"
                + (
                    f" on Branch {short_branch(registered)}"
                    if short_branch(registered)
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
    if commit_of(git, f"refs/heads/{branch}") is not None:
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
        if (name := short_branch(record)) is not None
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


def _add_worktree(git: Git, plan: WorktreePlan) -> None:
    """Run the one mutation, verify it, and roll back only what it created."""
    path = Path(plan.path)
    if plan.base_commit is None:
        # A plan with refusals never reaches here; a plan without a resolved
        # base is a programming error, and one -O must not silence.
        raise RuntimeError("worktree plan has no base commit to create from")
    created_directories = _make_directories(path.parent)
    with nonzero_exit_fails(WorktreeCreateError):
        result = git.run(
            "worktree", "add", "-b", plan.branch, str(path), plan.base_commit
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        leftovers = _roll_back(git, plan, created_directories)
        raise WorktreeCreateError(
            f"git worktree add failed: {detail}"
            + "".join(f"; {item}" for item in leftovers)
        )
    problems = _verify_worktree(git, plan)
    if problems:
        raise WorktreeCreateError(
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
        raise WorktreeCreateError(
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
    registered = registered_at(records, path)
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
                    f" on Branch {short_branch(registered)}"
                    if short_branch(registered)
                    else ""
                )
                + " and was left alone"
            )
        return messages
    branch_commit = commit_of(git, f"refs/heads/{plan.branch}")
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
    registered = registered_at(git.worktree_records(), path)
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
    chosen_by = plan.worktree_root_source
    if chosen_by == "default-sibling":
        # The default is derived, so say from what: a person reading the line
        # from a linked Worktree would otherwise expect its own sibling.
        chosen_by += f", beside the main working tree {plan.main_worktree}"
    lines.append(f"worktree root: {plan.worktree_root} (from {chosen_by})")
    lines.extend(f"existing Worktree hint: {item}" for item in plan.hints)
    lines.extend(f"warning: {item}" for item in plan.warnings)
    # Refusals are the CLI's to render from the structured ``plan.refusals``:
    # they are error-contract lines for stderr, not part of this report.
    return lines
