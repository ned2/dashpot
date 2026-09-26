"""Acceptance tests for the Project-local state directory that ignores itself in Git."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dashpot.core.project_state import ensure_state_directory
from dashpot.sessions.hook_publish import publish_hook_event
from dashpot.sessions.work import start_issue_work
from dashpot.sessions.work_store import ActiveWork, WorkStore
from factories import CODEX, EARLIER, dashpot_project, git, init_repository
from helpers import present, table_lookup

SESSION = "01a05099-1563-79a3-8504-e30d50949ca6"


@pytest.fixture(autouse=True)
def global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep the global hook store in the test's own directory."""
    directory = tmp_path / "global-state"
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(directory))
    return directory


def committed_project(root: Path) -> Path:
    """A configured Project whose own ``.gitignore`` has no rule for Dashpot state."""
    dashpot_project(root)
    git(root, "config", "user.email", "sim@example.invalid")
    git(root, "config", "user.name", "Sim")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "configure")
    assert not (root / ".gitignore").exists()
    return root


def publish(root: Path, event: str) -> Path:
    return publish_hook_event(
        {"session_id": SESSION, "cwd": str(root), "hook_event_name": event},
        process=CODEX,
        harness="codex",
        lookup=table_lookup({CODEX.pid: CODEX}),
    ).path


def active_work(root: Path) -> ActiveWork:
    return ActiveWork(
        session_key="codex-state",
        harness="codex",
        session_label="codex state",
        session_process=None,
        issue_id="I_a",
        issue_reference="I_a",
        binding_provenance="explicit-reference",
        started_at=EARLIER,
        working_directory=str(root),
        branch="main",
    )


def test_state_written_without_an_ignore_rule_leaves_the_worktree_clean(
    tmp_path: Path,
) -> None:
    root = committed_project(tmp_path / "repo").resolve()
    linked = tmp_path / "linked"
    git(root, "worktree", "add", "-q", "-b", "linked", str(linked))
    linked = linked.resolve()

    record = publish(root, "SessionStart")
    start_issue_work(
        root,
        "build-observer",
        lookup=present(CODEX),
        environ={"CODEX_THREAD_ID": SESSION},
    )
    # With a Work Store present, a Codex hook locks every Worktree's hook
    # store, creating the linked Worktree's state directory too.
    publish(root, "UserPromptSubmit")

    state = root / ".dashpot" / "state"
    assert record.parent == state / "sessions"
    assert [work.issue_reference for work in WorkStore(root).active()[0]] == [
        "build-observer"
    ]
    for worktree in (root, linked):
        assert (worktree / ".dashpot" / "state" / ".gitignore").read_text() == "*\n"
        assert git(worktree, "status", "--porcelain", "--untracked-files=all") == ""


def test_the_global_hook_store_gets_no_gitignore(
    tmp_path: Path, global_hook_store: Path
) -> None:
    unconfigured = init_repository(tmp_path / "unconfigured").resolve()

    record = publish(unconfigured, "SessionStart")

    assert record.parent == global_hook_store
    assert not (global_hook_store / ".gitignore").exists()
    assert not (unconfigured / ".dashpot").exists()


def test_an_existing_gitignore_is_never_replaced(tmp_path: Path) -> None:
    root = committed_project(tmp_path / "repo")
    state = root / ".dashpot" / "state"
    state.mkdir()
    (state / ".gitignore").write_text("work/\n")

    WorkStore(root).start(active_work(root))

    assert (state / ".gitignore").read_text() == "work/\n"


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root writes through directory permissions",
)
def test_a_gitignore_that_cannot_be_written_never_fails_the_state_write(
    tmp_path: Path,
) -> None:
    root = committed_project(tmp_path / "repo")
    store = WorkStore(root)
    store.directory.mkdir(parents=True)
    state = store.directory.parent
    state.chmod(0o555)
    try:
        store.start(active_work(root))
    finally:
        state.chmod(0o755)

    assert not (state / ".gitignore").exists()
    assert [work.session_key for work in store.active()[0]] == ["codex-state"]


def test_ensuring_the_directory_twice_keeps_one_gitignore(tmp_path: Path) -> None:
    first = ensure_state_directory(tmp_path)
    second = ensure_state_directory(tmp_path)

    assert first == second == tmp_path / ".dashpot" / "state"
    assert sorted(path.name for path in first.iterdir()) == [".gitignore"]
    assert (first / ".gitignore").read_text() == "*\n"
