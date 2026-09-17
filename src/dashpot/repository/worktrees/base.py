"""Resolve a Worktree base ref and its commit from Git facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ...core.git import Git
from ..repository import DEFAULT_BRANCHES, choose_integration_ref

BaseSource = Literal["--base", "origin/HEAD", "local-branch"]


@dataclass(frozen=True, slots=True)
class BaseResolution:
    """The chosen base ref, the rule that chose it, its commit, and any refusals."""

    ref: str | None
    source: BaseSource | None
    commit: str | None
    refusals: tuple[str, ...] = ()


def resolve_base(git: Git, option: str | None) -> BaseResolution:
    """The base ref, which rule chose it, and its exact commit; never fetched."""
    if option is not None:
        commit = commit_of(git, option)
        if commit is None:
            return BaseResolution(
                option,
                "--base",
                None,
                (f"--base {option} does not name a commit in this Repository",),
            )
        ref = git.maybe("rev-parse", "--symbolic-full-name", option) or option
        return BaseResolution(ref, "--base", commit)
    origin_head = git.maybe("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    origin_head = origin_head or None
    origin_commit = commit_of(git, origin_head) if origin_head is not None else None
    origin_refs = (
        [origin_head] if origin_head is not None and origin_commit is not None else []
    )
    ref = choose_integration_ref(origin_head, origin_refs)
    if ref is not None:
        return BaseResolution(ref, "origin/HEAD", origin_commit)
    # Each candidate ref is resolved exactly once; the chosen ref's commit is
    # reused rather than resolved again.
    commits = {
        f"refs/heads/{name}": commit
        for name in DEFAULT_BRANCHES
        if (commit := commit_of(git, f"refs/heads/{name}")) is not None
    }
    candidates = list(commits)
    ref = choose_integration_ref(None, candidates)
    if ref is not None:
        return BaseResolution(ref, "local-branch", commits[ref])
    local = [
        name.removeprefix("refs/heads/")
        for name in candidates
        if name.startswith("refs/heads/")
    ]
    return BaseResolution(
        None,
        None,
        None,
        (
            "no base Branch could be chosen: origin/HEAD is not set and there is "
            + ("no" if not local else "more than one")
            + " local main or master Branch; pass --base REF",
        ),
    )


def commit_of(git: Git, ref: str) -> str | None:
    """Resolve a named ref to its commit when Git can verify it."""
    commit = git.maybe(
        "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"
    )
    return commit or None
