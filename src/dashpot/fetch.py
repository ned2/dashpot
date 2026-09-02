"""Fetch the remotes of one Repository Anchor on explicit invocation.

Observation never fetches ([ADR 0005]); this module is the one named mutation
the dashboard performs, on the ``f`` key, and only against the Repository
Anchor whose refs supplied the current Branch observation ([ADR 0014]).

The Git invocation is ``git fetch --prune -- <remote>`` once per configured
remote, in ``git remote`` order, rather than a single ``git fetch --all``:
one call per remote attributes a failure to the remote that failed and lets
the others finish, so a partial failure is never reported as success.
``--prune`` drops the Remote-Tracking Branches that remote has deleted. No
refspec is passed, so each remote's configured refspec decides what arrives;
Dashpot never fetches a remote it did not configure. Every call runs under
Dashpot's Git timeout, non-interactively: ``GIT_TERMINAL_PROMPT=0`` stops
Git's own credential prompt, and the runner denies the command a controlling
terminal so an SSH prompt fails instead of taking over the screen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .commands import non_interactive_runner
from .git import Git, GitError

FETCH_ENVIRONMENT: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}


@dataclass(frozen=True, slots=True)
class RemoteFetch:
    """What fetching one remote came to."""

    remote: str
    ok: bool
    # The one-line reason when the fetch failed; empty for a success.
    detail: str = ""


@dataclass(frozen=True, slots=True)
class FetchReport:
    """What one explicit fetch did at one Repository Anchor.

    ``refusal`` is set when nothing was fetched at all: no remote is
    configured, or the remotes could not be listed. Otherwise every remote
    has its own result, in the order Git listed them.
    """

    anchor: str
    remotes: tuple[RemoteFetch, ...] = ()
    refusal: str | None = None

    @property
    def fetched(self) -> tuple[str, ...]:
        return tuple(result.remote for result in self.remotes if result.ok)

    @property
    def failed(self) -> tuple[RemoteFetch, ...]:
        return tuple(result for result in self.remotes if not result.ok)

    @property
    def succeeded(self) -> bool:
        """Every configured remote was fetched and pruned."""
        return self.refusal is None and not self.failed

    def summary(self) -> str:
        """One line for a toast or Diagnostic: what happened, remote by remote."""
        if self.refusal is not None:
            return self.refusal
        fetched = ", ".join(self.fetched)
        failures = "; ".join(f"{item.remote}: {item.detail}" for item in self.failed)
        if not failures:
            return f"fetched and pruned {fetched}"
        if fetched:
            return f"fetched and pruned {fetched}; failed {failures}"
        return f"failed {failures}"


RemoteFetcher = Callable[[Path], FetchReport]


def fetch_remotes(anchor: Path, *, git: Git) -> FetchReport:
    """Fetch and prune every configured remote of the Repository at ``anchor``.

    ``git`` must be a non-interactive adapter (see :func:`remote_fetcher`);
    it is retargeted at the anchor so the caller's root does not matter.
    """
    scoped = git.at(anchor)
    try:
        listed = scoped.text("remote")
    except GitError as exc:
        return FetchReport(str(anchor), refusal=f"cannot list remotes: {exc.detail}")
    remotes = [name for name in listed.splitlines() if name.strip()]
    if not remotes:
        return FetchReport(str(anchor), refusal="no remote is configured")
    results: list[RemoteFetch] = []
    for remote in remotes:
        try:
            result = scoped.run("fetch", "--prune", "--", remote)
        except GitError as exc:
            results.append(RemoteFetch(remote, False, exc.detail))
            continue
        if result.returncode != 0:
            results.append(RemoteFetch(remote, False, _failure_detail(result.stderr)))
            continue
        results.append(RemoteFetch(remote, True))
    return FetchReport(str(anchor), tuple(results))


def remote_fetcher(timeout: float) -> RemoteFetcher:
    """The production fetcher: a non-interactive Git adapter with Dashpot's timeout."""
    git = Git(Path.cwd(), timeout, non_interactive_runner(FETCH_ENVIRONMENT))
    return lambda anchor: fetch_remotes(anchor, git=git)


def _failure_detail(stderr: str) -> str:
    """Git's last non-empty stderr line: the reason, after any progress noise."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else "git fetch failed"
