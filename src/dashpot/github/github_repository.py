"""Identify a GitHub Repository: the reference a remote names, its durable id.

The mutable ``owner/name`` reference an origin remote names and the durable
identity GitHub answers for a reference are both facts about GitHub, not
about the Git observation ``repository.py`` performs, so they live beside the
gateway rather than in the module every Git-observing path imports.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from ..core.commands import CommandRunner, run_command
from ..core.errors import DashpotError
from ..core.git import Git
from .github import NOT_FOUND, GitHubGateway, GitHubRequestError

# The hosts a github.com remote names: SSH over port 443 uses the second.
_GITHUB_HOSTS = frozenset({"github.com", "ssh.github.com"})
_URL_SCHEMES = frozenset({"https", "http", "ssh", "git", "git+ssh", "ssh+git"})
# Git reads a remote with no "://" as scp-like only when a colon comes before
# any slash: ``[user@]host:path``.
_SCP_LIKE = re.compile(r"(?:[^@/]+@)?(?P<host>[^@/:]+):(?P<path>.+)")
# An Enterprise Managed User namespace adds an underscore to the owner.
_REFERENCE = re.compile(r"[A-Za-z0-9_-]+/(?!\.\.?$)[A-Za-z0-9._-]+")


def github_repo_from_remote(root: Path, git: Git | None = None) -> str | None:
    """Read the ``owner/name`` GitHub reference ``origin`` names, or None without one."""
    adapter = git if git is not None else Git(root)
    remote = adapter.at(root).maybe("remote", "get-url", "origin")
    return None if remote is None else github_repo_from_remote_url(remote)


def github_repo_from_remote_url(remote: str) -> str | None:
    """The ``owner/name`` a github.com remote URL names, or None for any other.

    The host must be exactly ``github.com`` or ``ssh.github.com``, so a host
    that merely ends in ``github.com`` names no GitHub repository. A port and
    a user are ignored, and one trailing slash and then a ``.git`` suffix,
    in any case, are removed.
    """
    text = remote.strip()
    if "://" in text:
        try:
            url = urlsplit(text)
        except ValueError:
            return None
        if url.scheme.casefold() not in _URL_SCHEMES or url.query or url.fragment:
            return None
        host, path = url.hostname, url.path
    else:
        match = _SCP_LIKE.fullmatch(text)
        if match is None:
            return None
        host, path = match["host"].casefold(), str(match["path"])
    if host not in _GITHUB_HOSTS:
        return None
    path = path.removeprefix("/").removesuffix("/")
    if path[-4:].casefold() == ".git":
        path = path[:-4]
    return path if _REFERENCE.fullmatch(path) else None


class RepositoryIdentityError(DashpotError):
    """A GitHub answer that names the repository without its durable identity."""


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
        raise RepositoryIdentityError(
            f"GitHub repository {reference} has no durable identity"
        )
    if not isinstance(observed_reference, str) or not observed_reference:
        raise RepositoryIdentityError(f"GitHub repository {reference} has no full name")
    return repository_id, observed_reference
