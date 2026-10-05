"""Name a Repository's Branch refs and choose its Integration Branch among them."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..core.git import Git

LOCAL_REF_PREFIX = "refs/heads/"
REMOTE_REF_PREFIX = "refs/remotes/"
ORIGIN_HEAD_REF = "refs/remotes/origin/HEAD"
DEFAULT_BRANCHES = ("main", "master")


def choose_integration_ref(
    origin_head: str | None, available_refs: Iterable[str]
) -> str | None:
    """Choose origin/HEAD, else the unique available local main or master ref.

    This is the one Integration Branch rule
    ([ADR 0012](../../../docs/adr/0012-observe-branch-integration-by-reachability.md)):
    Branch observation applies it to its own ref listing, while the Cleanup
    preview and Worktree removability apply it through ``RefIndex``.
    """
    refnames = set(available_refs)
    if origin_head is not None and origin_head in refnames:
        return origin_head
    local_defaults = [
        f"{LOCAL_REF_PREFIX}{name}"
        for name in DEFAULT_BRANCHES
        if f"{LOCAL_REF_PREFIX}{name}" in refnames
    ]
    return local_defaults[0] if len(local_defaults) == 1 else None


def branch_name(refname: str) -> str:
    """The Branch name of a local or Remote-Tracking ref."""
    if refname.startswith(LOCAL_REF_PREFIX):
        return refname.removeprefix(LOCAL_REF_PREFIX)
    if refname.startswith(REMOTE_REF_PREFIX):
        _remote, _slash, name = refname.removeprefix(REMOTE_REF_PREFIX).partition("/")
        return name
    return refname


def short_ref(refname: str) -> str:
    """A Branch ref as a person reads it: ``feat``, or ``origin/feat`` at a remote.

    For prose only; a command keeps the full ref, which a local Branch named
    like a Remote-Tracking Branch cannot shadow.
    """
    return refname.removeprefix(LOCAL_REF_PREFIX).removeprefix(REMOTE_REF_PREFIX)


@dataclass(frozen=True, slots=True)
class RefIndex:
    """Every Branch ref of a Repository: commit, commit time, and origin/HEAD."""

    commits: Mapping[str, str]
    committed_at: Mapping[str, str]
    origin_head: str | None

    @classmethod
    def read(cls, git: Git) -> RefIndex:
        """Index the local and Remote-Tracking Branch refs at ``git``."""
        records = git.records(
            "refs/heads",
            "refs/remotes",
            fields=(
                "%(refname)",
                "%(objectname)",
                "%(committerdate:iso-strict)",
                "%(symref)",
            ),
        )
        commits: dict[str, str] = {}
        committed_at: dict[str, str] = {}
        origin_head: str | None = None
        for refname, commit, committed, symref in records:
            if refname == ORIGIN_HEAD_REF:
                origin_head = symref or None
                continue
            if symref:
                continue
            commits[refname] = commit
            committed_at[refname] = committed
        return cls(commits, committed_at, origin_head)

    def integration_ref(self) -> str | None:
        """Choose the Integration Branch among the indexed refs."""
        return choose_integration_ref(self.origin_head, self.commits)
