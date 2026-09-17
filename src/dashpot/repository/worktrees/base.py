"""Resolve a Worktree base ref and its commit from Git facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ...core.git import Git
from ..repository import DEFAULT_BRANCHES, RefIndex

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
    # The Integration Branch rule chooses a new Worktree's base
    # ([ADR 0012](../../docs/adr/0012-observe-branch-integration-by-reachability.md)),
    # read through the same ref index the Cleanup preview inspects.
    refs = RefIndex.read(git)
    ref = refs.integration_ref()
    if ref is not None:
        source: BaseSource = (
            "origin/HEAD" if ref == refs.origin_head else "local-branch"
        )
        return BaseResolution(ref, source, refs.commits[ref])
    local = [name for name in DEFAULT_BRANCHES if f"refs/heads/{name}" in refs.commits]
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
