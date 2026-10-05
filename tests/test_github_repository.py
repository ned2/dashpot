"""The GitHub reference an origin remote names, read by its exact host."""

from __future__ import annotations

import pytest

from dashpot.github.github_repository import github_repo_from_remote_url


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/ned2/dashpot",
        "https://github.com/ned2/dashpot.git",
        "https://github.com/ned2/dashpot/",
        "https://github.com/ned2/dashpot.git/",
        "https://github.com/ned2/dashpot.GIT",
        "https://GitHub.com/ned2/dashpot",
        "https://token@github.com/ned2/dashpot.git",
        "https://github.com:443/ned2/dashpot.git",
        "ssh://git@github.com/ned2/dashpot.git",
        "ssh://git@github.com:22/ned2/dashpot.git",
        "ssh://git@ssh.github.com:443/ned2/dashpot.git",
        "git://github.com/ned2/dashpot.git",
        "git@github.com:ned2/dashpot.git",
        "git@github.com:ned2/dashpot/",
        "github.com:ned2/dashpot",
        "git@ssh.github.com:ned2/dashpot.git",
    ],
)
def test_a_github_com_remote_names_its_reference(remote: str) -> None:
    assert github_repo_from_remote_url(remote) == "ned2/dashpot"


def test_an_enterprise_managed_owner_keeps_its_underscore() -> None:
    assert (
        github_repo_from_remote_url("https://github.com/octocat_acme/dashpot.git")
        == "octocat_acme/dashpot"
    )


@pytest.mark.parametrize(
    "remote",
    [
        "https://notgithub.com/ned2/dashpot",
        "https://github.com.example.org/ned2/dashpot",
        "https://gist.github.com/ned2/dashpot",
        "git@notgithub.com:ned2/dashpot.git",
        "ssh://git@evilgithub.com/ned2/dashpot.git",
        "https://github.com/ned2",
        "https://github.com/ned2/dashpot/issues",
        "https://github.com/ned2/dashpot?tab=readme",
        "https://github.com//dashpot",
        "https://github.com/ned2/.",
        "https://github.com/ned2/..",
        "git@github.com:ned2/...git",
        "file://github.com/ned2/dashpot",
        "https://[github.com/ned2/dashpot",
        "/srv/git/ned2/dashpot.git",
        "../dashpot",
        "",
    ],
)
def test_any_other_remote_names_no_github_reference(remote: str) -> None:
    assert github_repo_from_remote_url(remote) is None
