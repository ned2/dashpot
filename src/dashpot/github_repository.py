"""Identify a GitHub Repository: the reference a remote names, its durable id.

The mutable ``owner/name`` reference an origin remote names and the durable
identity GitHub answers for a reference are both facts about GitHub, not
about the Git observation ``repository.py`` performs, so they live beside the
gateway rather than in the module every Git-observing path imports.
"""

from __future__ import annotations

import re
from pathlib import Path

from .commands import CommandRunner, run_command
from .git import Git
from .github import NOT_FOUND, GitHubGateway, GitHubRequestError


def github_repo_from_remote(root: Path, git: Git | None = None) -> str | None:
    """Read the ``owner/name`` GitHub reference ``origin`` names, or None without one."""
    adapter = git if git is not None else Git(root)
    remote = adapter.at(root).maybe("remote", "get-url", "origin")
    if remote is None:
        return None
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return None if match is None else str(match.group(1))


def observe_github_repository_identity(
    root: Path,
    reference: str,
    timeout: float = 10,
    runner: CommandRunner = run_command,
) -> tuple[str, str]:
    """Resolve a mutable GitHub reference to its durable Repository identity."""
    gateway = GitHubGateway(root, timeout=timeout, runner=runner)
    try:
        payload = gateway.rest(f"repos/{reference}")
    except GitHubRequestError as exc:
        # The one thing asked for by name is the repository, so a not-found
        # answer is the repository's; every other code is passed on as read.
        code = "github-repository" if exc.code == NOT_FOUND else exc.code
        raise GitHubRequestError(
            code, f"cannot resolve GitHub repository {reference}: {exc}"
        ) from exc
    repository_id = payload.get("node_id")
    observed_reference = payload.get("full_name")
    if not isinstance(repository_id, str) or not repository_id:
        raise RuntimeError(f"GitHub repository {reference} has no durable identity")
    if not isinstance(observed_reference, str) or not observed_reference:
        raise RuntimeError(f"GitHub repository {reference} has no full name")
    return repository_id, observed_reference
