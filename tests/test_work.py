from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dashpot.agents import ProcessIdentity, ProcessPresent
from dashpot.work import (
    identify_agent_session,
    show_issue_work,
    start_issue_work,
    stop_issue_work,
)
from dashpot.work_store import WorkStore
from helpers import absent, present

CODEX = ProcessIdentity(4242, 1, "codex", "Tue Aug 25 01:00:00 2026")


def codex_lookup(_pid: int) -> ProcessPresent:
    return ProcessPresent(CODEX)


def issue_document(*, issue_id: str, number: int, reference: str, title: str) -> str:
    metadata = {
        "id": issue_id,
        "number": number,
        "reference": reference,
        "state": "open",
        "stateReason": None,
        "labels": [],
        "assignees": [],
        "author": "ned",
        "relationships": {
            "parent": None,
            "subIssues": [],
            "blockedBy": [],
            "blocking": [],
        },
        "issueType": None,
        "milestone": None,
        "createdAt": "2026-08-26T05:33:04Z",
        "updatedAt": "2026-08-26T08:32:48Z",
        "closedAt": None,
    }
    return "\n".join(
        ["---", json.dumps(metadata, indent=2), "---", f"# {title}", "", "Body.", ""]
    )


def repository(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".dashpot").mkdir()
    (root / ".dashpot" / "config.json").write_text(
        json.dumps(
            {
                "projectId": "project:test",
                "displayLabel": "Test",
                "repositoryId": "repository:test",
                "issueSource": {"kind": "markdown", "path": "issues"},
            }
        )
    )
    issues = root / "issues"
    issues.mkdir()
    (issues / "build-observer.md").write_text(
        issue_document(
            issue_id="I_observer",
            number=1,
            reference="build-observer",
            title="Build observer",
        )
    )
    (issues / "fix-crash.md").write_text(
        issue_document(
            issue_id="I_crash",
            number=2,
            reference="fix-crash",
            title="Fix crash",
        )
    )
    return root


def issue_ids(root: Path) -> dict[str, str]:
    active, _ = WorkStore(root).active()
    return {item.session_key: item.issue_id for item in active}


def test_start_resolves_reference_and_records_active_work(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    messages = start_issue_work(root, "build-observer", lookup=codex_lookup)

    active, diagnostics = WorkStore(root).active()
    assert diagnostics == []
    assert len(active) == 1
    assert active[0].issue_reference == "build-observer"
    assert active[0].binding_provenance == "explicit-reference"
    assert active[0].harness == "codex"
    assert active[0].session_process is not None
    assert active[0].session_process.pid == 4242
    assert "started work on build-observer" in messages[0]


def test_switch_ends_the_old_run_and_begins_a_new_one(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    first, _ = WorkStore(root).active()

    messages = start_issue_work(root, "fix-crash", lookup=codex_lookup)

    second, _ = WorkStore(root).active()
    assert len(second) == 1
    assert second[0].issue_id != first[0].issue_id
    assert second[0].run_id != first[0].run_id
    assert "switched from build-observer to fix-crash" in messages[0]


def test_stop_ends_work_while_the_session_stays_identifiable(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)

    messages = stop_issue_work(root, lookup=codex_lookup)

    active, _ = WorkStore(root).active()
    assert active == []
    assert messages == ["stopped work on build-observer"]
    assert stop_issue_work(root, lookup=codex_lookup) == [
        "no active Issue work for this session"
    ]


def test_stop_by_session_key_ends_an_orphaned_run_without_a_session(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    (session_key,) = issue_ids(root)

    messages = stop_issue_work(root, session_key=session_key, lookup=absent())

    active, _ = WorkStore(root).active()
    assert active == []
    assert messages == ["stopped orphaned work on build-observer for codex pid 4242"]
    assert stop_issue_work(root, session_key=session_key, lookup=absent()) == [
        f"no active Issue work recorded for session {session_key}"
    ]


def test_stop_by_session_key_refuses_a_live_session(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    (session_key,) = issue_ids(root)

    with pytest.raises(RuntimeError, match="still running"):
        stop_issue_work(root, session_key=session_key, lookup=present(CODEX))

    active, _ = WorkStore(root).active()
    assert len(active) == 1


def test_show_lists_active_work_at_the_worktree(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    assert show_issue_work(root) == ["no active Issue work at this worktree"]

    start_issue_work(root, "build-observer", lookup=codex_lookup)

    messages = show_issue_work(root)
    assert len(messages) == 1
    assert "build-observer" in messages[0]
    assert "codex pid 4242" in messages[0]


def test_opt_in_requires_an_enclosing_supported_session(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    with pytest.raises(RuntimeError, match="supported agent session"):
        start_issue_work(root, "build-observer", lookup=absent())


def test_unmatched_reference_is_an_actionable_error(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    with pytest.raises(RuntimeError, match="did not match an Issue"):
        start_issue_work(root, "no-such-issue", lookup=codex_lookup)

    active, _ = WorkStore(root).active()
    assert active == []


def test_unavailable_issue_source_defers_resolution(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    (root / ".dashpot" / "config.json").write_text(
        json.dumps(
            {
                "projectId": "project:test",
                "displayLabel": "Test",
                "repositoryId": "repository:test",
                "issueSource": {"kind": "markdown", "path": "missing"},
            }
        )
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        start_issue_work(root, "build-observer", lookup=codex_lookup)


def test_session_identity_is_stable_for_one_process(tmp_path: Path) -> None:
    first = identify_agent_session(codex_lookup)
    second = identify_agent_session(codex_lookup)

    assert first == second
    assert first.session_key.startswith("codex-4242-")


CLAUDE = ProcessIdentity(7777, 1, "claude", "Tue Aug 25 02:00:00 2026")


def test_claude_code_session_can_opt_into_issue_work(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    messages = start_issue_work(root, "build-observer", lookup=present(CLAUDE))

    active, _ = WorkStore(root).active()
    assert active[0].harness == "claude-code"
    assert active[0].session_key.startswith("claude-code-7777-")
    assert "started work on build-observer" in messages[0]


def test_codex_and_claude_code_runs_on_one_issue_are_independent(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    start_issue_work(root, "build-observer", lookup=present(CLAUDE))

    active, _ = WorkStore(root).active()

    assert len(active) == 2
    assert {work.harness for work in active} == {"codex", "claude-code"}
    assert len({work.run_id for work in active}) == 2
