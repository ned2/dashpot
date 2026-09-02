"""Acceptance tests for ``worktree create`` and ``worktree check``.

Every test runs against a disposable Local Issue Markdown repository ("Sim")
with Issues 35 and 36, a ``main`` Branch, and a tag ``pre-config`` that
predates ``.dashpot/config.json``; nothing talks to the network.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dashpot import worktrees
from dashpot.commands import CommandResult, run_command
from dashpot.git import Git
from dashpot.hook_records import session_directory, write_hook_record
from dashpot.model import Diagnostic
from dashpot.processes import ProcessIdentity
from dashpot.serialization import (
    removability_document,
    worktree_plan_document,
)
from dashpot.settings import Settings
from dashpot.work_store import ActiveWork, SessionProcess, WorkStore
from dashpot.worktrees import (
    check_worktree,
    create_issue_worktree,
    default_branch_name,
    describe_removability,
    describe_worktree_plan,
    resolve_worktree_root,
    title_slug,
)
from factories import WORKTREE_PROTOCOL_ISSUES, git, write_issues
from helpers import absent, make_issue, table_lookup

CONFIG = {
    "projectId": "project:sim",
    "displayLabel": "Sim",
    "repositoryId": "repository:sim",
    "issueSource": {"kind": "markdown", "path": "issues"},
}


def sim(tmp_path: Path, *, origin_head: bool = True) -> Path:
    """A configured Sim at ``tmp_path/p/sim`` on ``main``, committed."""
    root = tmp_path / "p" / "sim"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "sim@example.invalid")
    git(root, "config", "user.name", "Sim")
    (root / "README.md").write_text("Sim\n")
    (root / ".gitignore").write_text(".dashpot/state/\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "before configuration")
    git(root, "tag", "pre-config")
    (root / ".dashpot").mkdir()
    (root / ".dashpot" / "config.json").write_text(json.dumps(CONFIG))
    write_issues(root, WORKTREE_PROTOCOL_ISSUES)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "configure")
    if origin_head:
        # A fetched remote default Branch, without any network: the
        # Remote-Tracking Branch and origin/HEAD that a clone would have.
        git(root, "remote", "add", "origin", str(tmp_path / "never-fetched.git"))
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(
            root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"
        )
    return root


def create(
    root: Path,
    hint: str = "35",
    *,
    base: str | None = None,
    branch: str | None = None,
    worktree_root_option: Path | None = None,
    dry_run: bool = False,
    git_adapter: Git | None = None,
) -> worktrees.WorktreePlan:
    return create_issue_worktree(
        root,
        hint,
        base=base,
        branch=branch,
        worktree_root_option=worktree_root_option,
        dry_run=dry_run,
        environ={},
        settings=Settings(),
        git=git_adapter,
    )


def worktree_paths(root: Path) -> list[str]:
    return [
        line.split()[0]
        for line in git(root, "worktree", "list").splitlines()
        if line.strip()
    ]


def local_branches(root: Path) -> set[str]:
    return set(
        git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    )


def assert_main_unchanged(root: Path, branches: set[str]) -> None:
    assert git(root, "status", "--porcelain") == ""
    assert local_branches(root) == branches


# --- Default naming and root -------------------------------------------------


def test_default_creates_the_sibling_worktree_on_the_issue_branch(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)

    plan = create(root)

    expected = tmp_path / "p" / "sim.worktrees" / "worktree-protocol"
    assert plan.created is True
    assert plan.path == str(expected)
    assert plan.branch == "worktree-protocol"
    assert plan.base_ref == "refs/remotes/origin/main"
    assert plan.base_source == "origin/HEAD"
    assert plan.base_commit == git(root, "rev-parse", "HEAD")
    assert plan.worktree_root == str(tmp_path / "p" / "sim.worktrees")
    assert plan.worktree_root_source == "default-sibling"
    assert plan.refusals == ()
    assert expected in [Path(item) for item in worktree_paths(root)]
    assert git(expected, "symbolic-ref", "--short", "HEAD") == "worktree-protocol"
    assert git(expected, "rev-parse", "HEAD") == plan.base_commit
    assert git(expected, "status", "--porcelain") == ""
    assert git(root, "status", "--porcelain") == ""
    assert not (root / ".dashpot" / "state").exists()


def test_json_shape_names_every_source(tmp_path: Path) -> None:
    root = sim(tmp_path)

    payload = worktree_plan_document(create(root))

    assert set(payload) == {
        "issueId",
        "issueReference",
        "path",
        "branch",
        "baseRef",
        "baseSource",
        "baseCommit",
        "worktreeRoot",
        "worktreeRootSource",
        "dryRun",
        "created",
        "refusals",
        "hints",
        "warnings",
    }
    assert payload["issueId"] == "I_35"
    assert payload["created"] is True


def test_github_issue_branch_follows_githubs_convention() -> None:
    issue = make_issue(
        number=35,
        title="Add `dashpot worktree create` & check: for Issue Worktrees!",
        reference="ned2/dashpot#35",
    )

    assert (
        default_branch_name(issue) == "35-add-dashpot-worktree-create-check-for-issue"
    )
    assert default_branch_name(make_issue(number=35, title="***")) == "35"


def test_title_slug_cuts_at_a_word_boundary() -> None:
    assert title_slug("Hello, World") == "hello-world"
    assert len(title_slug("word " * 40)) <= worktrees.SLUG_LIMIT
    assert title_slug("x" * 100) == "x" * worktrees.SLUG_LIMIT


def test_local_main_is_the_reported_guess_without_origin_head(tmp_path: Path) -> None:
    root = sim(tmp_path, origin_head=False)

    plan = create(root)

    assert plan.created is True
    assert plan.base_ref == "refs/heads/main"
    assert plan.base_source == "local-branch"


def test_without_origin_head_or_one_local_default_branch_base_is_required(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path, origin_head=False)
    git(root, "branch", "master")
    branches = local_branches(root)

    plan = create(root)

    assert plan.created is False
    assert plan.base_commit is None
    assert any("pass --base REF" in item for item in plan.refusals)
    assert worktree_paths(root) == [str(root)]
    assert_main_unchanged(root, branches)


def test_explicit_base_is_resolved_to_its_commit(tmp_path: Path) -> None:
    root = sim(tmp_path)
    git(root, "branch", "feature")

    plan = create(root, base="feature")

    assert plan.base_ref == "refs/heads/feature"
    assert plan.base_source == "--base"
    assert plan.base_commit == git(root, "rev-parse", "feature")
    assert plan.created is True


def test_unknown_base_is_refused(tmp_path: Path) -> None:
    root = sim(tmp_path)

    plan = create(root, base="nowhere")

    assert plan.refusals == (
        "--base nowhere does not name a commit in this Repository",
    )


def test_worktree_root_precedence(tmp_path: Path) -> None:
    anchor = tmp_path / "p" / "sim"
    settings = Settings(worktree_root=tmp_path / "from-settings")
    environment = {"DASHPOT_WORKTREE_ROOT": str(tmp_path / "from-env")}

    assert resolve_worktree_root(
        anchor, tmp_path / "from-option", environment, settings
    ) == (tmp_path / "from-option", "--worktree-root")
    assert resolve_worktree_root(anchor, None, environment, settings) == (
        tmp_path / "from-env",
        "DASHPOT_WORKTREE_ROOT",
    )
    assert resolve_worktree_root(anchor, None, {}, settings) == (
        tmp_path / "from-settings",
        "settings",
    )
    assert resolve_worktree_root(anchor, None, {}, Settings()) == (
        tmp_path / "p" / "sim.worktrees",
        "default-sibling",
    )


def test_worktree_root_is_real_path_normalised(tmp_path: Path) -> None:
    root = sim(tmp_path)
    real = tmp_path / "real-root"
    real.mkdir()
    link = tmp_path / "link-root"
    link.symlink_to(real)

    plan = create(root, worktree_root_option=link, dry_run=True)

    assert plan.worktree_root == str(real)
    assert plan.path == str(real / "worktree-protocol")


def test_root_inside_a_worktree_of_the_project_is_refused(tmp_path: Path) -> None:
    root = sim(tmp_path)
    branches = local_branches(root)

    plan = create(root, worktree_root_option=root / ".claude" / "worktrees")

    assert plan.created is False
    assert any("inside the Worktree" in item for item in plan.refusals)
    assert not (root / ".claude").exists()
    assert_main_unchanged(root, branches)


# --- Base predating configuration ---------------------------------------------


def test_base_predating_configuration_fails_before_creation(tmp_path: Path) -> None:
    root = sim(tmp_path)
    branches = local_branches(root)

    plan = create(root, base="pre-config")

    assert plan.created is False
    assert len(plan.refusals) == 1
    assert "has no .dashpot/config.json" in plan.refusals[0]
    assert worktree_paths(root) == [str(root)]
    assert not (tmp_path / "p" / "sim.worktrees").exists()
    assert_main_unchanged(root, branches)


def test_base_configuring_another_project_is_refused(tmp_path: Path) -> None:
    root = sim(tmp_path)
    git(root, "checkout", "-q", "-b", "fork")
    (root / ".dashpot" / "config.json").write_text(
        json.dumps({**CONFIG, "projectId": "project:fork"})
    )
    git(root, "commit", "-q", "-am", "re-initialise")
    git(root, "checkout", "-q", "main")

    plan = create(root, base="fork")

    assert plan.created is False
    assert "projectId project:fork" in plan.refusals[0]
    assert "different Project" in plan.refusals[0]


# --- Path and Branch collisions ------------------------------------------------


def test_two_approaches_to_one_issue(tmp_path: Path) -> None:
    root = sim(tmp_path)
    first = create(root)

    again = create(root)
    alternate = create(root, branch="35-alternate")

    assert again.created is False
    assert again.hints == (f"{first.path} (Branch worktree-protocol)",)
    assert any("looks like Issue #35's already exists" in r for r in again.refusals)
    assert alternate.created is True
    assert alternate.branch == "35-alternate"
    assert alternate.path == str(tmp_path / "p" / "sim.worktrees" / "35-alternate")
    assert git(root, "status", "--porcelain") == ""


def test_existing_worktree_starting_with_the_issue_number_is_a_hint(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    git(root, "worktree", "add", "-q", "-b", "35-earlier-attempt", str(elsewhere))

    plan = create(root)

    assert plan.created is False
    assert plan.hints == (f"{elsewhere} (Branch 35-earlier-attempt)",)
    assert create(root, branch="35-second").created is True


def test_non_empty_path_is_refused(tmp_path: Path) -> None:
    root = sim(tmp_path)
    target = tmp_path / "p" / "sim.worktrees" / "worktree-protocol"
    target.mkdir(parents=True)
    (target / "keep").write_text("")

    plan = create(root)

    assert plan.refusals == (f"{target} exists and is not empty",)
    assert (target / "keep").exists()


def test_empty_directory_dashpot_did_not_create_is_refused(tmp_path: Path) -> None:
    root = sim(tmp_path)
    target = tmp_path / "p" / "sim.worktrees" / "worktree-protocol"
    target.mkdir(parents=True)

    plan = create(root)

    assert plan.created is False
    assert "empty directory Dashpot did not create" in plan.refusals[0]
    assert target.is_dir()


def test_existing_and_checked_out_branches_are_refused(tmp_path: Path) -> None:
    root = sim(tmp_path)
    git(root, "branch", "worktree-protocol")

    existing = create(root)
    assert any(
        item == "Branch worktree-protocol already exists; pass --branch NAME for a "
        "separate approach"
        for item in existing.refusals
    )

    checked_out = create(root, branch="main")
    assert any(
        f"Branch main already exists and is checked out at {root}" in item
        for item in checked_out.refusals
    )


@pytest.mark.parametrize("name", ["main/alt", "bad..name", "-leading", "space name"])
def test_invalid_and_slash_extending_branch_names_are_refused(
    tmp_path: Path, name: str
) -> None:
    root = sim(tmp_path)
    branches = local_branches(root)

    plan = create(root, branch=name)

    assert plan.created is False
    assert plan.refusals
    assert_main_unchanged(root, branches)


def test_a_branch_that_is_a_prefix_of_an_existing_branch_is_refused(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)
    git(root, "branch", "35/alt")

    plan = create(root, branch="35")

    assert any("prefix of the existing Branch 35/alt" in r for r in plan.refusals)


def test_slash_in_the_branch_becomes_a_hyphen_in_the_path(tmp_path: Path) -> None:
    root = sim(tmp_path)

    plan = create(root, branch="feature/35-nested")

    assert plan.created is True
    assert plan.path == str(tmp_path / "p" / "sim.worktrees" / "feature-35-nested")


# --- Dry run --------------------------------------------------------------------


def test_dry_run_reports_the_plan_and_refusals_without_creating(tmp_path: Path) -> None:
    root = sim(tmp_path)
    branches = local_branches(root)

    plan = create(root, dry_run=True)
    refused = create(root, base="pre-config", dry_run=True)

    assert plan.dry_run is True
    assert plan.created is False
    assert plan.refusals == ()
    assert plan.path == str(tmp_path / "p" / "sim.worktrees" / "worktree-protocol")
    assert refused.refusals and "has no .dashpot/config.json" in refused.refusals[0]
    assert worktree_paths(root) == [str(root)]
    assert not (tmp_path / "p" / "sim.worktrees").exists()
    assert_main_unchanged(root, branches)
    assert describe_worktree_plan(plan)[0].startswith("would create Worktree ")
    # Refusals stay on the structured field for the CLI to render on stderr;
    # the report lines carry everything else.
    assert refused.refusals
    assert not any(
        line.startswith("refused: ") for line in describe_worktree_plan(refused)
    )


def test_settings_diagnostics_ride_the_plan_as_warnings(tmp_path: Path) -> None:
    root = sim(tmp_path)
    machine = Settings(
        diagnostics=(
            Diagnostic(
                source="settings:/tmp/settings.json",
                severity="warning",
                message="Ignoring unknown Dashpot settings fields: bogus",
                code="settings-unknown-field",
            ),
        )
    )

    plan = create_issue_worktree(root, "35", dry_run=True, environ={}, settings=machine)

    assert plan.refusals == ()
    assert plan.warnings == ("Ignoring unknown Dashpot settings fields: bogus",)
    assert (
        "warning: Ignoring unknown Dashpot settings fields: bogus"
        in describe_worktree_plan(plan)
    )


# --- Concurrent creators and partial failure -----------------------------------


def test_concurrent_creators_yield_one_worktree_one_branch_and_one_error(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)

    def attempt(_index: int) -> worktrees.WorktreePlan | RuntimeError:
        try:
            return create(root)
        except RuntimeError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    plans = [item for item in outcomes if isinstance(item, worktrees.WorktreePlan)]
    errors = [item for item in outcomes if isinstance(item, RuntimeError)]
    created = [plan for plan in plans if plan.created]
    expected = str(tmp_path / "p" / "sim.worktrees" / "worktree-protocol")
    assert len(created) == 1
    # The loser failed either in Git (an error naming the winner) or on a
    # refusal computed after the winner finished.
    assert len(errors) + len([plan for plan in plans if plan.refusals]) == 1
    for error in errors:
        assert "git worktree add failed" in str(error)
        assert f"at {expected}" in str(error)
    assert worktree_paths(root) == [str(root), expected]
    assert local_branches(root) == {"main", "worktree-protocol"}
    assert git(root, "status", "--porcelain") == ""


def test_lost_race_rolls_back_only_the_branch_this_invocation_created(
    tmp_path: Path,
) -> None:
    """A ``git worktree add`` that fails after creating its Branch."""
    root = sim(tmp_path)
    base = git(root, "rev-parse", "HEAD")

    def failing_add(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if list(args[:3]) == ["git", "worktree", "add"]:
            git(root, "branch", "worktree-protocol", base)
            return CommandResult(list(args), 128, "", "fatal: simulated failure")
        return run_command(args, cwd, timeout)

    with pytest.raises(RuntimeError) as failure:
        create(root, git_adapter=Git(root, runner=failing_add))

    message = str(failure.value)
    assert "git worktree add failed: fatal: simulated failure" in message
    assert "removed the Branch worktree-protocol this command created" in message
    assert local_branches(root) == {"main"}
    assert worktree_paths(root) == [str(root)]
    assert not (tmp_path / "p" / "sim.worktrees").exists()
    assert git(root, "status", "--porcelain") == ""


def test_a_branch_left_pointing_elsewhere_is_never_deleted(tmp_path: Path) -> None:
    root = sim(tmp_path)

    def failing_add(args: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
        if list(args[:3]) == ["git", "worktree", "add"]:
            git(root, "branch", "worktree-protocol", "pre-config")
            return CommandResult(list(args), 128, "", "fatal: simulated failure")
        return run_command(args, cwd, timeout)

    with pytest.raises(RuntimeError, match="not at the base commit"):
        create(root, git_adapter=Git(root, runner=failing_add))

    assert "worktree-protocol" in local_branches(root)


def test_partially_created_worktree_is_reported_with_recovery_and_left_alone(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)
    first = create(root)
    # A killed `git worktree add` leaves exactly this signature: a registered
    # Worktree locked `initializing` and its Branch.
    git(root, "worktree", "lock", "--reason", "initializing", first.path)
    before = git(root, "worktree", "list", "--porcelain")

    plan = create(root)

    assert plan.created is False
    partial = [item for item in plan.refusals if "partially created" in item]
    assert len(partial) == 1
    assert f"git worktree remove -f -f {first.path}" in partial[0]
    assert "git branch -D worktree-protocol" in partial[0]
    assert git(root, "worktree", "list", "--porcelain") == before


def test_unwritable_root_is_an_actionable_error(tmp_path: Path) -> None:
    root = sim(tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("")

    with pytest.raises(RuntimeError, match="cannot create the Worktree root"):
        create(root, worktree_root_option=blocked / "worktrees")

    assert local_branches(root) == {"main"}


# --- Removability report ---------------------------------------------------------


def test_clean_idle_worktree_is_removable(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)

    report = check_worktree(root, Path(plan.path))

    assert report.removable is True
    assert report.obstacles == ()
    assert report.branch == "worktree-protocol"
    assert report.role == "linked"
    assert report.remove_commands == (
        f"git worktree remove {plan.path}",
        "git branch -d worktree-protocol",
    )
    assert describe_removability(report)[0].endswith("is removable")
    payload = removability_document(report)
    assert payload["removable"] is True
    assert payload["obstacles"] == []


def test_check_reports_each_obstacle_with_its_command(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)
    path = Path(plan.path)
    (path / "scratch.txt").write_text("")
    git(path, "commit", "-q", "--allow-empty", "-m", "local work")
    git(root, "worktree", "lock", "--reason", "claude pid 4242", plan.path)
    gone = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")
    WorkStore(path).start(
        ActiveWork(
            session_key="codex-4242-deadbeef",
            harness="codex",
            session_label="codex pid 4242",
            session_process=SessionProcess(pid=gone.pid, started_at=gone.started_at),
            issue_id="I_35",
            issue_reference="worktree-protocol",
            binding_provenance="explicit-reference",
            started_at="2026-08-30T03:34:35.830802Z",
            working_directory=str(path),
            branch="worktree-protocol",
            session_id=None,
        )
    )
    live = ProcessIdentity(7777, 1, "claude", "Tue Aug 25 02:00:00 2026")
    write_hook_record(
        {
            "version": 2,
            "sessionId": "01c7192b-2990-4f83-ad33-290ac22eb4d1",
            "harness": "claude-code",
            "state": "running",
            "cwd": str(path),
            "repositoryRoot": str(path),
            "branch": "worktree-protocol",
            "event": "UserPromptSubmit",
            "lastActivityAt": "2026-08-30T03:40:00.000000Z",
            "sessionProcess": live.as_record(),
        },
        session_directory(path),
    )
    before = git(root, "worktree", "list", "--porcelain")

    report = check_worktree(
        root,
        path,
        lookup=table_lookup({gone.pid: gone, live.pid: live}),
        lock_probe=lambda _pid: "gone",
    )

    assert report.removable is False
    by_kind = {obstacle.kind: obstacle for obstacle in report.obstacles}
    assert set(by_kind) == {
        "dirty",
        "locked",
        "agent-session",
        "agent-run",
        "unpushed",
        "unmerged",
    }
    assert by_kind["dirty"].command == f"git worktree remove --force {path}"
    assert by_kind["locked"].detail == "locked: claude pid 4242 (holding process gone)"
    assert by_kind["locked"].command == f"git worktree unlock {path}"
    assert "Claude Code session 01c7192b" in by_kind["agent-session"].detail
    assert by_kind["agent-run"].command == "dashpot work stop (inside that session)"
    assert (
        by_kind["unpushed"].command == f"git -C {path} push -u origin worktree-protocol"
    )
    assert by_kind["unmerged"].detail == (
        "1 commit(s) not reachable from refs/remotes/origin/main"
    )
    assert git(root, "worktree", "list", "--porcelain") == before
    assert (path / "scratch.txt").exists()
    lines = describe_removability(report)
    assert lines[0].endswith("is not removable:")
    assert len(lines) == 1 + len(report.obstacles)


def test_orphaned_run_names_the_stop_command(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)
    path = Path(plan.path)
    WorkStore(path).start(
        ActiveWork(
            session_key="codex-4242-deadbeef",
            harness="codex",
            session_label="codex pid 4242",
            session_process=SessionProcess(
                pid=4242, started_at="Tue Aug 25 01:00:00 2026"
            ),
            issue_id="I_35",
            issue_reference="worktree-protocol",
            binding_provenance="explicit-reference",
            started_at="2026-08-30T03:34:35.830802Z",
            working_directory=str(path),
            branch="worktree-protocol",
        )
    )

    report = check_worktree(root, path, lookup=absent())

    (obstacle,) = report.obstacles
    assert obstacle.kind == "agent-run"
    assert obstacle.detail.startswith("Orphaned Agent Run on worktree-protocol")
    assert obstacle.command == (
        f"cd {path} && dashpot work stop --session codex-4242-deadbeef"
    )


def test_an_unreadable_work_store_record_is_an_obstacle(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)
    path = Path(plan.path)
    work = WorkStore(path).directory
    work.mkdir(parents=True)
    (work / "codex-4242-deadbeef.json").write_text("{not json")

    report = check_worktree(root, path, lookup=absent())

    # The record may describe a live Agent Run; removable is never claimed
    # on evidence that could not be read.
    assert report.removable is False
    (obstacle,) = report.obstacles
    assert obstacle.kind == "work-store"
    assert "Cannot read Work Store record" in obstacle.detail


def test_no_integration_branch_is_reported_not_assumed_merged(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)
    path = Path(plan.path)
    git(path, "commit", "-q", "--allow-empty", "-m", "local work")
    git(root, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    git(root, "branch", "-m", "main", "trunk")

    report = check_worktree(root, path)

    assert report.removable is False
    by_kind = {obstacle.kind: obstacle for obstacle in report.obstacles}
    assert "unmerged" in by_kind
    assert by_kind["unmerged"].detail.startswith(
        "cannot tell whether Branch worktree-protocol is integrated: "
        "no base Branch could be chosen"
    )


def test_initializing_lock_names_the_forced_removal(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)
    git(root, "worktree", "lock", "--reason", "initializing", plan.path)

    report = check_worktree(root, Path(plan.path))

    (obstacle,) = report.obstacles
    assert obstacle.kind == "locked"
    assert obstacle.command == f"git worktree remove -f -f {plan.path}"


def test_pushed_branch_with_upstream_is_not_unpushed(tmp_path: Path) -> None:
    root = sim(tmp_path)
    plan = create(root)
    path = Path(plan.path)
    git(path, "commit", "-q", "--allow-empty", "-m", "work")
    git(
        root, "update-ref", "refs/remotes/origin/worktree-protocol", "worktree-protocol"
    )
    git(path, "branch", "--set-upstream-to=origin/worktree-protocol")

    report = check_worktree(root, path)

    assert [obstacle.kind for obstacle in report.obstacles] == ["unmerged"]
    assert report.obstacles[0].command == (
        "git log --oneline refs/remotes/origin/main..worktree-protocol"
    )


def test_main_worktree_is_never_removable(tmp_path: Path) -> None:
    root = sim(tmp_path)

    report = check_worktree(root, root)

    assert report.role == "main"
    assert report.removable is False
    assert report.obstacles[0].kind == "main-worktree"
    assert report.remove_commands == ()


def test_check_refuses_a_path_that_is_not_a_worktree(tmp_path: Path) -> None:
    root = sim(tmp_path)

    with pytest.raises(RuntimeError, match="is not a Worktree of the Repository"):
        check_worktree(root, tmp_path / "nowhere")


def test_squash_merged_worktree_is_removable_with_a_forced_branch_delete(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)
    plan = create(root)
    worktree = Path(plan.path)
    (worktree / "feature.py").write_text("feature\n")
    git(worktree, "add", "feature.py")
    git(worktree, "commit", "-q", "-m", "feature work")
    git(root, "merge", "--squash", "-q", plan.branch)
    git(root, "commit", "-q", "-m", "feature work (#35)")
    # The squash landed on the remote default Branch and was fetched.
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    report = check_worktree(root, worktree)

    assert report.obstacles == ()
    assert report.removable is True
    assert report.remove_commands == (
        f"git worktree remove {plan.path}",
        f"git branch -D {plan.branch}",
    )


def test_linked_worktrees_lists_every_linked_worktree_but_the_main(
    tmp_path: Path,
) -> None:
    root = sim(tmp_path)
    assert worktrees.linked_worktrees(root) == []

    first = create(root)
    second = create(root, "36")

    listed = worktrees.linked_worktrees(Path(second.path))
    assert listed == sorted([Path(first.path).resolve(), Path(second.path).resolve()])
