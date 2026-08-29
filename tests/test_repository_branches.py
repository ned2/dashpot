from __future__ import annotations

from pathlib import Path

from dashpot.repository import BRANCH_REF_FORMAT, observe_branches
from test_repository_targets import SequenceRunner, completed


def ref(
    refname: str,
    head: str = "abc123",
    upstream: str = "",
    track: str = "",
    committed_at: str = "2026-08-27T13:00:00+10:00",
    worktree: str = "",
    symref: str = "",
) -> str:
    return "\0".join([refname, head, upstream, track, committed_at, worktree, symref])


def test_observes_local_and_remote_tracking_branches_without_fetching(
    tmp_path: Path,
) -> None:
    anchor = tmp_path / "repo"
    common_dir = anchor / ".git"
    common_dir.mkdir(parents=True)
    (common_dir / "FETCH_HEAD").write_text("")
    listing = "\n".join(
        [
            ref("refs/heads/main", "aaa", "origin/main", "", worktree=str(anchor)),
            ref("refs/heads/feature", "bbb", "origin/feature", "[ahead 2, behind 1]"),
            ref("refs/heads/local-only", "ccc"),
            ref("refs/heads/orphan", "ddd", "origin/orphan", "[gone]"),
            ref("refs/remotes/origin/HEAD", "aaa", symref="refs/remotes/origin/main"),
            ref("refs/remotes/origin/main", "aaa"),
            ref("refs/remotes/origin/feature", "eee"),
            ref("refs/remotes/upstream/main", "fff"),
            ref("refs/tags/not-a-branch", "999"),
        ]
    )
    runner = SequenceRunner(completed(listing + "\n"), completed(".git\n"))

    observation = observe_branches([anchor], runner=runner)

    assert observation.diagnostics == []
    assert [call[0] for call in runner.calls] == [
        [
            "git",
            "for-each-ref",
            f"--format={BRANCH_REF_FORMAT}",
            "refs/heads",
            "refs/remotes",
        ],
        ["git", "rev-parse", "--git-common-dir"],
    ]
    # Every git call that is made is a listing: nothing fetches.
    assert not any("fetch" in call[0] for call in runner.calls)
    by_ref = {branch.refname: branch for branch in observation.branches}
    assert list(by_ref) == [
        "refs/heads/main",
        "refs/heads/feature",
        "refs/heads/local-only",
        "refs/heads/orphan",
        "refs/remotes/origin/main",
        "refs/remotes/origin/feature",
        "refs/remotes/upstream/main",
    ]
    main = by_ref["refs/heads/main"]
    assert (main.name, main.remote, main.upstream) == ("main", None, "origin/main")
    assert (main.ahead, main.behind, main.upstream_gone) == (0, 0, False)
    assert main.checked_out_at == str(anchor)
    assert main.committed_at == "2026-08-27T03:00:00Z"
    feature = by_ref["refs/heads/feature"]
    assert (feature.ahead, feature.behind, feature.upstream_gone) == (2, 1, False)
    local_only = by_ref["refs/heads/local-only"]
    assert (local_only.upstream, local_only.ahead, local_only.behind) == (
        None,
        None,
        None,
    )
    assert by_ref["refs/heads/orphan"].upstream_gone is True
    upstream_main = by_ref["refs/remotes/upstream/main"]
    assert (upstream_main.name, upstream_main.remote) == ("main", "upstream")
    assert upstream_main.upstream is None
    assert observation.fetched_at is not None
    assert observation.fetched_at.endswith("Z")


def test_first_answering_anchor_is_authoritative_and_failures_are_diagnosed(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken"
    working = tmp_path / "working"
    runner = SequenceRunner(
        completed("", stderr="fatal: not a git repository", returncode=128),
        completed(ref("refs/heads/main", "aaa") + "\n"),
        OSError("git missing"),
    )

    observation = observe_branches([broken, working], runner=runner)

    assert [branch.refname for branch in observation.branches] == ["refs/heads/main"]
    # A repository that never fetched has no FETCH_HEAD; a failed lookup of
    # the common directory is the same honest answer.
    assert observation.fetched_at is None
    assert observation.diagnostics == []
    assert [call[1] for call in runner.calls] == [broken, working, working]


def test_every_anchor_failing_reports_each_one() -> None:
    runner = SequenceRunner(OSError("no git"), completed("", "boom", 1))

    observation = observe_branches([Path("/a"), Path("/b")], runner=runner)

    assert observation.branches == []
    assert observation.fetched_at is None
    assert [(item.source, item.code) for item in observation.diagnostics] == [
        ("anchor:/a", "branch-discovery"),
        ("anchor:/b", "branch-discovery"),
    ]
    assert observation.diagnostics[1].message == "Cannot list Branches: boom"
