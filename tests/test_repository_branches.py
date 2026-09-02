from __future__ import annotations

from pathlib import Path

from dashpot.git import Git
from dashpot.repository import observe_branches
from factories import SequenceRunner, completed, git, ref_stream


def over(runner: SequenceRunner) -> Git:
    """A Git adapter over ``runner``; the observer retargets it per anchor."""
    return Git(Path("/unused"), runner=runner)


def ref(
    refname: str,
    head: str = "abc123",
    upstream: str = "",
    track: str = "",
    committed_at: str = "2026-08-27T13:00:00+10:00",
    worktree: str = "",
    symref: str = "",
) -> tuple[str, ...]:
    return (refname, head, upstream, track, committed_at, worktree, symref)


def test_observes_local_and_remote_tracking_branches_without_fetching(
    tmp_path: Path,
) -> None:
    anchor = tmp_path / "repo"
    common_dir = anchor / ".git"
    common_dir.mkdir(parents=True)
    (common_dir / "FETCH_HEAD").write_text("")
    listing = ref_stream(
        ref("refs/heads/main", "aaa", "origin/main", "", worktree=str(anchor)),
        ref("refs/heads/feature", "bbb", "origin/feature", "[ahead 2, behind 1]"),
        ref("refs/heads/local-only", "ccc"),
        ref("refs/heads/orphan", "ddd", "origin/orphan", "[gone]"),
        ref("refs/remotes/origin/HEAD", "aaa", symref="refs/remotes/origin/main"),
        ref("refs/remotes/origin/main", "aaa"),
        ref("refs/remotes/origin/feature", "eee"),
        ref("refs/remotes/upstream/main", "fff"),
        ref("refs/tags/not-a-branch", "999"),
    )
    runner = SequenceRunner(
        completed(listing),
        completed(
            ref_stream(
                ("refs/heads/main",),
                ("refs/heads/local-only",),
                ("refs/remotes/origin/main",),
                ("refs/remotes/origin/feature",),
                ("refs/remotes/upstream/main",),
            )
        ),
        # feature: two retained commits whose merge leaves main's tree as is.
        completed("2\n"),
        completed("tree-main\n"),
        completed("tree-main\n"),
        completed("base\n"),
        completed("src/feature.py\0"),
        # orphan: one retained commit, a conflicting merge, and no squash
        # commit on main touching what it changed.
        completed("1\n"),
        completed("tree-main\n"),
        completed("tree-conflict\n", returncode=1),
        completed("base\n"),
        completed("src/orphan.py\0"),
        completed("c" * 40 + "\n\nsrc/other.py\n"),
        completed(".git\n"),
    )

    observation = observe_branches([anchor], git=over(runner))

    assert observation.diagnostics == []
    assert observation.anchor == str(anchor)
    # The adapter owns the exact argv; the seam asserts the verbs and the
    # operands that carry the observation's meaning.
    assert [call[0][1] for call in runner.calls] == [
        "for-each-ref",
        "for-each-ref",
        "rev-list",
        "rev-parse",
        "merge-tree",
        "merge-base",
        "diff",
        "rev-list",
        "rev-parse",
        "merge-tree",
        "merge-base",
        "diff",
        "log",
        "rev-parse",
    ]
    assert runner.calls[0][0][-2:] == ["refs/heads", "refs/remotes"]
    assert runner.calls[1][0][-2:] == ["refs/heads", "refs/remotes"]
    assert "--merged=refs/remotes/origin/main" in runner.calls[1][0]
    assert "refs/remotes/origin/main..refs/heads/feature" in runner.calls[2][0]
    assert runner.calls[4][0][-2:] == ["refs/remotes/origin/main", "refs/heads/feature"]
    assert "refs/remotes/origin/main..refs/heads/orphan" in runner.calls[7][0]
    assert runner.calls[12][0][1:3] == ["log", "--first-parent"]
    assert "base..refs/remotes/origin/main" in runner.calls[12][0]
    assert "--git-common-dir" in runner.calls[13][0]
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
    assert main.unintegrated_commits == 0
    assert main.checked_out_at == str(anchor)
    assert main.committed_at == "2026-08-27T03:00:00Z"
    feature = by_ref["refs/heads/feature"]
    assert (feature.ahead, feature.behind, feature.upstream_gone) == (2, 1, False)
    assert feature.unintegrated_commits == 2
    assert feature.content_integrated is True
    local_only = by_ref["refs/heads/local-only"]
    assert (local_only.upstream, local_only.ahead, local_only.behind) == (
        None,
        None,
        None,
    )
    assert local_only.unintegrated_commits == 0
    assert by_ref["refs/heads/orphan"].upstream_gone is True
    assert by_ref["refs/heads/orphan"].unintegrated_commits == 1
    assert by_ref["refs/heads/orphan"].content_integrated is False
    assert main.content_integrated is None
    assert local_only.content_integrated is None
    upstream_main = by_ref["refs/remotes/upstream/main"]
    assert (upstream_main.name, upstream_main.remote) == ("main", "upstream")
    assert upstream_main.upstream is None
    assert upstream_main.unintegrated_commits == 0
    assert by_ref["refs/remotes/origin/feature"].unintegrated_commits == 0
    assert observation.integration_ref == "refs/remotes/origin/main"
    assert observation.fetched_at is not None
    assert observation.fetched_at.endswith("Z")


def test_first_answering_anchor_is_authoritative_and_failures_are_diagnosed(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken"
    working = tmp_path / "working"
    runner = SequenceRunner(
        completed("", stderr="fatal: not a git repository", returncode=128),
        completed(ref_stream(ref("refs/heads/main", "aaa"))),
        completed(ref_stream(("refs/heads/main",))),
        OSError("git missing"),
    )

    observation = observe_branches([broken, working], git=over(runner))

    assert [branch.refname for branch in observation.branches] == ["refs/heads/main"]
    # The clone that answered is the one an explicit fetch may mutate.
    assert observation.anchor == str(working)
    # A repository that never fetched has no FETCH_HEAD; a failed lookup of
    # the common directory is the same honest answer.
    assert observation.fetched_at is None
    assert observation.integration_ref == "refs/heads/main"
    assert observation.branches[0].unintegrated_commits == 0
    # The answering anchor stays authoritative, but the broken one is still
    # surfaced as a warning (issue #77 owner decision).
    assert [
        (item.source, item.code, item.severity) for item in observation.diagnostics
    ] == [(f"anchor:{broken}", "branch-discovery", "warning")]
    assert [call[1] for call in runner.calls] == [
        broken,
        working,
        working,
        working,
    ]


def test_every_anchor_failing_reports_each_one() -> None:
    runner = SequenceRunner(OSError("no git"), completed("", "boom", 1))

    observation = observe_branches([Path("/a"), Path("/b")], git=over(runner))

    assert observation.branches == []
    assert observation.fetched_at is None
    assert observation.integration_ref is None
    assert observation.anchor is None
    assert [(item.source, item.code) for item in observation.diagnostics] == [
        ("anchor:/a", "branch-discovery"),
        ("anchor:/b", "branch-discovery"),
    ]
    assert observation.diagnostics[1].message == "Cannot list Branches: boom"


def test_ambiguous_local_defaults_leave_integration_unavailable() -> None:
    listing = ref_stream(ref("refs/heads/main", "aaa"), ref("refs/heads/master", "bbb"))
    runner = SequenceRunner(completed(listing), completed(".git\n"))

    observation = observe_branches([Path("/repo")], git=over(runner))

    assert observation.integration_ref is None
    assert all(branch.unintegrated_commits is None for branch in observation.branches)
    assert [call[0][1] for call in runner.calls] == ["for-each-ref", "rev-parse"]


def test_a_failing_integration_listing_is_a_diagnostic_not_an_absence() -> None:
    listing = ref_stream(
        ref("refs/heads/main", "aaa"),
        ref("refs/remotes/origin/HEAD", "aaa", symref="refs/remotes/origin/main"),
        ref("refs/remotes/origin/main", "aaa"),
    )
    runner = SequenceRunner(
        completed(listing),
        completed("", stderr="fatal: bad object", returncode=128),
        completed(".git\n"),
    )

    observation = observe_branches([Path("/repo")], git=over(runner))

    assert observation.integration_ref == "refs/remotes/origin/main"
    by_ref = {branch.refname: branch for branch in observation.branches}
    assert by_ref["refs/heads/main"].unintegrated_commits is None
    assert [(item.code, item.severity) for item in observation.diagnostics] == [
        ("branch-integration", "warning")
    ]
    assert "fatal: bad object" in observation.diagnostics[0].message


def test_a_failing_commit_count_is_a_diagnostic_not_an_absence() -> None:
    listing = ref_stream(
        ref("refs/heads/main", "aaa"),
        ref("refs/heads/feature", "bbb"),
        ref("refs/remotes/origin/HEAD", "aaa", symref="refs/remotes/origin/main"),
        ref("refs/remotes/origin/main", "aaa"),
    )
    runner = SequenceRunner(
        completed(listing),
        completed(ref_stream(("refs/heads/main",), ("refs/remotes/origin/main",))),
        completed("", stderr="fatal: bad revision", returncode=128),
        completed(".git\n"),
    )

    observation = observe_branches([Path("/repo")], git=over(runner))

    by_ref = {branch.refname: branch for branch in observation.branches}
    assert by_ref["refs/heads/main"].unintegrated_commits == 0
    assert by_ref["refs/heads/feature"].unintegrated_commits is None
    assert [item.code for item in observation.diagnostics] == ["branch-integration"]
    assert "refs/heads/feature" in observation.diagnostics[0].message


# --- Content integration against real Git (ADR 0017) -------------------------


def _commit(root: Path, path: str, text: str, message: str) -> None:
    (root / path).write_text(text)
    git(root, "add", path)
    git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "-m",
        message,
    )


def squash_repository(tmp_path: Path) -> Path:
    """``main`` with a squash-merged ``done``, a live ``pending``, and a ``kept``.

    ``done`` is squash-merged and its file is then edited again on ``main``, so
    merging its tip conflicts and only the squash scan can recognise it.
    ``pending`` is squash-merged with nothing on ``main`` since, so merging
    its tip changes nothing. ``kept`` holds work that never landed.
    """
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    _commit(root, "app.py", "one\n", "seed")
    git(root, "branch", "done")
    git(root, "branch", "kept")
    git(root, "checkout", "-q", "done")
    _commit(root, "app.py", "one\ntwo\n", "add two")
    _commit(root, "app.py", "one\ntwo\nthree\n", "add three")
    git(root, "checkout", "-q", "kept")
    _commit(root, "kept.py", "kept\n", "kept work")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "--squash", "-q", "done")
    git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "-m",
        "add two and three (#1)",
    )
    _commit(root, "app.py", "one\ntwo\nthree\nfour\n", "add four")
    git(root, "checkout", "-q", "-b", "pending")
    _commit(root, "app.py", "one\ntwo\nthree\nfour\nfive\n", "add five")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "--squash", "-q", "pending")
    git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "-m",
        "add five (#2)",
    )
    return root


def test_squash_merged_branches_are_integrated_by_content(tmp_path: Path) -> None:
    root = squash_repository(tmp_path)

    observation = observe_branches([root])

    assert observation.diagnostics == []
    by_name = {branch.name: branch for branch in observation.branches}
    assert by_name["main"].unintegrated_commits == 0
    assert by_name["main"].content_integrated is None
    # Merging the tip changes nothing: recognised at the first step.
    assert by_name["pending"].unintegrated_commits == 1
    assert by_name["pending"].content_integrated is True
    # Merging the tip conflicts; the squash commit is found on main.
    assert by_name["done"].unintegrated_commits == 2
    assert by_name["done"].content_integrated is True
    # Work that never landed is retained work.
    assert by_name["kept"].unintegrated_commits == 1
    assert by_name["kept"].content_integrated is False


def test_remote_tracking_branches_are_assessed_for_integration(tmp_path: Path) -> None:
    root = squash_repository(tmp_path)
    for name in ("main", "done", "pending", "kept"):
        git(root, "update-ref", f"refs/remotes/origin/{name}", f"refs/heads/{name}")
    git(
        root,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        "refs/remotes/origin/main",
    )
    git(root, "branch", "-D", "done", "pending", "kept")

    observation = observe_branches([root])

    assert observation.diagnostics == []
    by_name = {
        branch.name: branch
        for branch in observation.branches
        if branch.remote == "origin"
    }
    assert by_name["main"].unintegrated_commits == 0
    assert by_name["main"].content_integrated is None
    assert by_name["pending"].unintegrated_commits == 1
    assert by_name["pending"].content_integrated is True
    assert by_name["done"].unintegrated_commits == 2
    assert by_name["done"].content_integrated is True
    assert by_name["kept"].unintegrated_commits == 1
    assert by_name["kept"].content_integrated is False


def test_content_integration_never_fetches_or_mutates(tmp_path: Path) -> None:
    root = squash_repository(tmp_path)
    before = git(root, "for-each-ref")
    status = git(root, "status", "--porcelain")

    observe_branches([root])

    assert git(root, "for-each-ref") == before
    assert git(root, "status", "--porcelain") == status
