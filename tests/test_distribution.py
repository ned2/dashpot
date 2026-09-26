"""The running Dashpot is described from its distribution's and source's own files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashpot.core import distribution
from dashpot.core.distribution import (
    DistributionFacts,
    describe_distribution,
    installed_distribution,
    process_start,
    source_dirty,
    source_revision,
)
from dashpot.core.runtime_events import InstallKind
from factories import git, init_repository

COMMIT = "a" * 40
OTHER = "b" * 40


def dist_info(root: Path, *, version: str = "1.2.3", direct: object = None) -> Path:
    directory = root / f"dashpot-{version}.dist-info"
    directory.mkdir(parents=True)
    (directory / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: dashpot\nVersion: {version}\n\nVersion: 9\n"
    )
    if direct is not None:
        (directory / "direct_url.json").write_text(
            direct if isinstance(direct, str) else json.dumps(direct)
        )
    return directory


def test_a_wheel_from_an_index_has_no_direct_url(tmp_path: Path) -> None:
    assert describe_distribution(dist_info(tmp_path)) == DistributionFacts(
        version="1.2.3", install_kind="wheel"
    )


def test_a_vcs_install_reports_the_commit_it_was_built_from(tmp_path: Path) -> None:
    direct = {
        "url": "https://github.com/ned2/dashpot",
        "vcs_info": {"vcs": "git", "commit_id": COMMIT},
    }

    assert describe_distribution(dist_info(tmp_path, direct=direct)) == (
        DistributionFacts(version="1.2.3", install_kind="vcs", revision=COMMIT)
    )


def test_a_vcs_commit_that_is_no_object_id_is_unknown(tmp_path: Path) -> None:
    direct = {"url": "x", "vcs_info": {"vcs": "git", "commit_id": "main; rm -rf"}}

    assert describe_distribution(dist_info(tmp_path, direct=direct)).revision == (
        "unknown"
    )


def test_an_archive_install_names_itself(tmp_path: Path) -> None:
    direct = {"url": "https://example.invalid/dashpot.tar.gz", "archive_info": {}}

    assert describe_distribution(dist_info(tmp_path, direct=direct)) == (
        DistributionFacts(version="1.2.3", install_kind="archive")
    )


@pytest.mark.parametrize(
    ("editable", "kind"),
    [(True, "editable"), (False, "directory"), (None, "directory")],
)
def test_a_directory_install_reads_its_source_checkouts_commit(
    tmp_path: Path, editable: bool | None, kind: InstallKind
) -> None:
    source = init_repository(tmp_path / "source with space")
    git(source, "commit", "-q", "--allow-empty", "-m", "first")
    info = {} if editable is None else {"editable": editable}
    direct = {"url": (source.as_uri()), "dir_info": info}

    facts = describe_distribution(dist_info(tmp_path / "site", direct=direct))

    assert facts == DistributionFacts(
        version="1.2.3",
        install_kind=kind,
        revision=git(source, "rev-parse", "HEAD"),
        source=source,
    )


@pytest.mark.parametrize(
    "direct",
    [
        "not json",
        "[]",
        json.dumps({"url": "x"}),
        json.dumps({"dir_info": {}, "url": 3}),
    ],
    ids=["malformed", "not-an-object", "no-kind", "no-file-url"],
)
def test_an_unreadable_direct_url_is_unknown(tmp_path: Path, direct: str) -> None:
    facts = describe_distribution(dist_info(tmp_path, direct=direct))

    assert facts.version == "1.2.3"
    assert facts.revision == "unknown"
    assert facts.install_kind in {"unknown", "directory"}


def test_no_distribution_is_all_unknown(tmp_path: Path) -> None:
    assert describe_distribution(None) == DistributionFacts()
    assert describe_distribution(tmp_path / "missing.dist-info").version == "unknown"


def test_the_distribution_is_found_on_the_search_path(tmp_path: Path) -> None:
    (tmp_path / "dashpot-0.0.1.dist-info").mkdir()
    found = dist_info(tmp_path / "site")

    # A wheel keeps its dist-info beside the imported package, which is tried
    # before the search path; an editable checkout keeps none there.
    beside_package = installed_distribution([])

    assert installed_distribution([str(tmp_path), str(tmp_path / "site")]) == (
        beside_package or found
    )
    assert installed_distribution([str(tmp_path / "missing")]) == beside_package


# --- Source revision --------------------------------------------------------


def test_a_branch_head_is_read_from_its_loose_ref(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git" / "refs" / "heads").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (checkout / ".git" / "refs" / "heads" / "main").write_text(f"{COMMIT}\n")

    assert source_revision(checkout) == COMMIT


def test_a_packed_branch_is_read_from_packed_refs(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (checkout / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{OTHER} refs/heads/other\n"
        f"{COMMIT} refs/heads/main\n"
    )

    assert source_revision(checkout) == COMMIT


def test_a_detached_head_is_its_own_commit(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text(f"{COMMIT}\n")

    assert source_revision(checkout) == COMMIT


def test_a_linked_worktree_is_followed_to_its_shared_refs(tmp_path: Path) -> None:
    main = init_repository(tmp_path / "main")
    git(main, "commit", "-q", "--allow-empty", "-m", "first")
    git(main, "branch", "feature")
    linked = tmp_path / "linked"
    git(main, "worktree", "add", "-q", str(linked), "feature")
    git(linked, "commit", "-q", "--allow-empty", "-m", "second")
    git(main, "pack-refs", "--all")

    assert source_revision(linked) == git(linked, "rev-parse", "HEAD")
    assert source_revision(linked) != git(main, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    "head",
    ["ref: refs/heads/missing\n", "garbage\n", "ref: refs/heads/main\n"],
    ids=["unborn", "garbage", "reftable"],
)
def test_a_head_that_names_no_readable_commit_is_unknown(
    tmp_path: Path, head: str
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git" / "refs" / "heads").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text(head)
    # A reftable Repository keeps a placeholder where the loose ref would be.
    (checkout / ".git" / "refs" / "heads" / "main").write_text("this is not a ref\n")

    assert source_revision(checkout) == "unknown"


def test_a_directory_that_is_no_checkout_is_unknown(tmp_path: Path) -> None:
    assert source_revision(tmp_path) == "unknown"
    (tmp_path / ".git").write_text("not a pointer\n")
    assert source_revision(tmp_path) == "unknown"


# --- Source dirtiness and process facts --------------------------------------


def test_a_source_checkout_with_changes_is_dirty(tmp_path: Path) -> None:
    source = init_repository(tmp_path / "source")
    git(source, "commit", "-q", "--allow-empty", "-m", "first")

    assert source_dirty(source) is False
    (source / "new.txt").write_text("x")
    assert source_dirty(source) is True
    assert source_dirty(tmp_path / "missing") is None
    assert source_dirty(tmp_path) is None


def test_a_process_is_described_with_its_source_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = init_repository(tmp_path / "source")
    monkeypatch.setattr(
        distribution,
        "running_distribution",
        lambda: DistributionFacts(
            version="1.2.3", install_kind="editable", revision=COMMIT, source=source
        ),
    )

    plain = process_start(tmp_path, subcommand="work show")
    checked = process_start(None, check_source=True)

    assert (plain.version, plain.install_kind, plain.revision) == (
        "1.2.3",
        "editable",
        COMMIT,
    )
    assert plain.working_directory == str(tmp_path)
    assert plain.subcommand == "work show"
    assert plain.source_dirty is None
    assert checked.source_dirty is False
    assert checked.working_directory is None


def test_facts_that_do_not_fit_their_fields_are_recorded_as_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        distribution,
        "running_distribution",
        lambda: DistributionFacts(version="1.2.3 (patched: see notes)"),
    )

    facts = process_start(Path("relative"), subcommand="work show")

    assert facts.version == "unknown"
    assert facts.working_directory is None
    assert facts.subcommand is None


def test_a_version_is_read_from_the_metadata_headers_only(tmp_path: Path) -> None:
    directory = tmp_path / "dashpot-1.0.dist-info"
    directory.mkdir()
    (directory / "METADATA").write_text("Name: dashpot\n\nVersion: 9\n")

    assert describe_distribution(directory).version == "unknown"


def test_a_directory_install_from_a_remote_url_has_no_source(tmp_path: Path) -> None:
    direct = {"url": "https://example.invalid/dashpot", "dir_info": {}}

    facts = describe_distribution(dist_info(tmp_path, direct=direct))

    assert (facts.install_kind, facts.source, facts.revision) == (
        "directory",
        None,
        "unknown",
    )


def test_a_search_path_entry_that_cannot_be_listed_is_passed_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = dist_info(tmp_path / "site")
    real_glob = Path.glob

    def glob(self: Path, pattern: str) -> object:
        if self == tmp_path / "locked":
            raise PermissionError(13, "Permission denied")
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", glob)
    beside_package = installed_distribution([])

    assert installed_distribution(
        [str(tmp_path / "locked"), str(tmp_path / "site")]
    ) == (beside_package or found)


def test_a_ref_missing_from_packed_refs_or_unreadable_is_unknown(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (checkout / ".git" / "packed-refs").write_text(f"{OTHER} refs/heads/other\n")

    assert source_revision(checkout) == "unknown"
    (checkout / ".git" / "HEAD").unlink()
    (checkout / ".git" / "HEAD").mkdir()
    assert source_revision(checkout) == "unknown"
