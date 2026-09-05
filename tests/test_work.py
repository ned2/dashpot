from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from dashpot.agents import observe_agent_runs
from dashpot.errors import DashpotError
from dashpot.harnesses import SESSION_OVERRIDE_VARIABLE
from dashpot.hook_records import (
    publish_hook_event,
    session_directory,
    state_directory,
)
from dashpot.model import ObservationTarget
from dashpot.processes import ProcessIdentity, ProcessLookup, ProcessPresent
from dashpot.work import (
    identify_agent_session,
    relocate_issue_work,
    show_issue_work,
    start_issue_work,
    stop_issue_work,
)
from dashpot.work_store import SessionProcess, WorkStore
from factories import (
    CLAUDE,
    CODEX,
    EARLIER,
    LATER,
    dashpot_project,
    hook_record,
    legacy_ended_record,
    write_project_config,
)
from helpers import absent, present, table_lookup, unobservable


def codex_lookup(_pid: int) -> ProcessPresent:
    return ProcessPresent(CODEX)


@pytest.fixture(autouse=True)
def _global_hook_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the global hook store in the test's own directory."""
    monkeypatch.setenv("DASHPOT_STATE_DIR", str(tmp_path / "global-state"))


def repository(root: Path) -> Path:
    return dashpot_project(root)


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


def test_stop_by_session_key_refuses_an_identity_route_session_still_placed(
    tmp_path: Path,
) -> None:
    # A sandboxed session whose hook could not publish a host process is
    # recorded by Agent Session Identity alone; its hook record is the only
    # evidence of liveness, and an unended one is not evidence it is over.
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", None)
    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON)
    (session_key,) = issue_ids(root)
    (work,) = WorkStore(root).active()[0]
    assert work.session_process is None

    with pytest.raises(RuntimeError, match="still running"):
        stop_issue_work(root, session_key=session_key, lookup=absent())
    assert len(WorkStore(root).active()[0]) == 1

    hook_record(root, CODEX_SESSION, "codex", None, state="ended")
    messages = stop_issue_work(root, session_key=session_key, lookup=absent())

    assert messages[0].startswith("stopped orphaned work on build-observer")
    assert WorkStore(root).active()[0] == []


def test_show_lists_active_work_at_the_worktree(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    assert show_issue_work(root) == ["no active Issue work at this worktree"]

    start_issue_work(root, "build-observer", lookup=codex_lookup)

    messages = show_issue_work(root)
    assert len(messages) == 1
    assert "build-observer" in messages[0]
    assert "codex pid 4242" in messages[0]


def test_a_version_one_work_store_record_remains_readable(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    (path,) = WorkStore(root).directory.glob("*.json")
    record = json.loads(path.read_text())
    record["version"] = 1
    record.pop("relocation", None)
    path.write_text(json.dumps(record))

    active, diagnostics = WorkStore(root).active()

    assert len(active) == 1
    assert active[0].relocation is None
    assert diagnostics == []


def test_a_version_one_record_cannot_claim_version_two_relocation_semantics(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    (path,) = WorkStore(root).directory.glob("*.json")
    record = json.loads(path.read_text())
    record["version"] = 1
    record["relocation"] = {
        "targetWorktree": "/other",
        "requestedAt": "2026-09-05T05:20:00.000000Z",
    }
    path.write_text(json.dumps(record))

    active, diagnostics = WorkStore(root).active()

    assert active == []
    assert "version 1" in diagnostics[0].message


def test_start_refuses_when_this_sessions_own_record_is_unreadable(
    tmp_path: Path,
) -> None:
    # Writing beside an unreadable record for this session's key would leave
    # two records for one session, so the start is a refusal (issue #77 O-A5).
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    (record_path,) = WorkStore(root).directory.glob("*.json")
    record_path.write_text("not json")

    with pytest.raises(DashpotError, match="Cannot read Work Store record"):
        start_issue_work(root, "fix-crash", lookup=codex_lookup)

    assert sorted(WorkStore(root).directory.glob("*.json")) == [record_path]


def test_start_surfaces_other_sessions_unreadable_records(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    corrupt = WorkStore(root).directory / "other-session.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not json")

    messages = start_issue_work(root, "build-observer", lookup=codex_lookup)

    assert "started work on build-observer" in messages[0]
    assert any("Cannot read Work Store record" in message for message in messages)


def test_stop_surfaces_unreadable_records_beside_the_outcome(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    corrupt = WorkStore(root).directory / "other-session.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not json")

    messages = stop_issue_work(root, lookup=codex_lookup)

    assert messages[0] == "no active Issue work for this session"
    assert "Cannot read Work Store record" in messages[1]


def test_stop_by_session_key_refuses_an_unreadable_record(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    start_issue_work(root, "build-observer", lookup=codex_lookup)
    (session_key,) = issue_ids(root)
    WorkStore(root).record_path(session_key).write_text("not json")

    with pytest.raises(DashpotError, match="Cannot read Work Store record"):
        stop_issue_work(root, session_key=session_key, lookup=absent())


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
    write_project_config(root, issue_source={"kind": "markdown", "path": "missing"})

    with pytest.raises(RuntimeError, match="unavailable"):
        start_issue_work(root, "build-observer", lookup=codex_lookup)


def test_session_identity_is_stable_for_one_process(tmp_path: Path) -> None:
    first = identify_agent_session(codex_lookup)
    second = identify_agent_session(codex_lookup)

    assert first == second
    assert first.session_key.startswith("codex-4242-")


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


def test_bare_issue_number_resolves_like_the_prefixed_hint(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    start_issue_work(root, "2", lookup=codex_lookup)
    bare, _ = WorkStore(root).active()
    start_issue_work(root, "#2", lookup=codex_lookup)
    prefixed, _ = WorkStore(root).active()

    assert bare[0].issue_id == "I_crash"
    assert prefixed[0].issue_id == bare[0].issue_id
    assert prefixed[0].issue_reference == bare[0].issue_reference == "fix-crash"


# --- Sandboxed Agent Sessions: identity by Agent Session Identity -----------

ISOLATED = unobservable("isolated-namespace")
CODEX_SESSION = "01a05099-1563-79a3-8504-e30d50949ca6"
CLAUDE_SESSION = "01c7192b-2990-4f83-ad33-290ac22eb4d1"
CODEX_ENVIRON = {"CODEX_THREAD_ID": CODEX_SESSION}
CLAUDE_ENVIRON = {"CLAUDE_CODE_SESSION_ID": CLAUDE_SESSION, "CLAUDE_PID": "7777"}


def test_isolated_namespace_without_a_claim_reproduces_the_gap(tmp_path: Path) -> None:
    """The real sandbox lookup result, and no identity, is the #53 failure."""
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)

    with pytest.raises(RuntimeError, match="isolated process namespace") as failure:
        start_issue_work(root, "build-observer", lookup=ISOLATED, environ={})

    assert "no supported agent session encloses this command" in str(failure.value)
    assert "dashpot integrate <harness> --status" in str(failure.value)
    active, _ = WorkStore(root).active()
    assert active == []


def test_codex_session_opts_in_from_its_sandbox_by_hook_identity(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)

    messages = start_issue_work(
        root, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON
    )

    active, diagnostics = WorkStore(root).active()
    assert diagnostics == []
    assert len(active) == 1
    work = active[0]
    assert work.harness == "codex"
    assert work.session_id == CODEX_SESSION
    # The hook published the harness's host process; the record keys and
    # labels the session exactly as the process route would have.
    assert work.session_process == SessionProcess(
        pid=CODEX.pid, started_at=CODEX.started_at
    )
    assert work.session_key.startswith("codex-4242-")
    assert work.session_label == "codex pid 4242"
    assert "started work on build-observer" in messages[0]


def test_claude_code_session_opts_in_from_a_hidden_ancestry_by_hook_identity(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)

    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CLAUDE_ENVIRON)

    active, _ = WorkStore(root).active()
    assert active[0].harness == "claude-code"
    assert active[0].session_id == CLAUDE_SESSION
    assert active[0].session_key.startswith("claude-code-7777-")


def test_claude_code_with_visible_ancestry_records_its_corroborated_identity(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)

    start_issue_work(
        root, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )

    active, _ = WorkStore(root).active()
    assert active[0].session_key.startswith("claude-code-7777-")
    assert active[0].session_id == CLAUDE_SESSION


def test_visible_ancestry_ignores_a_claim_that_does_not_corroborate(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    other = ProcessIdentity(9999, 1, "claude", "Tue Aug 25 03:00:00 2026")
    hook_record(root, CLAUDE_SESSION, "claude-code", other)

    start_issue_work(
        root,
        "build-observer",
        lookup=present(CLAUDE),
        environ={"CLAUDE_CODE_SESSION_ID": CLAUDE_SESSION},
    )

    active, _ = WorkStore(root).active()
    assert active[0].session_process == SessionProcess(
        pid=CLAUDE.pid, started_at=CLAUDE.started_at
    )
    assert active[0].session_id is None


def test_identity_route_is_stable_across_start_switch_and_stop(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)

    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON)
    first, _ = WorkStore(root).active()
    switched = start_issue_work(
        root, "fix-crash", lookup=ISOLATED, environ=CODEX_ENVIRON
    )
    second, _ = WorkStore(root).active()
    stopped = stop_issue_work(root, lookup=ISOLATED, environ=CODEX_ENVIRON)

    assert "switched from build-observer to fix-crash" in switched[0]
    assert len(second) == 1
    assert second[0].session_key == first[0].session_key
    assert second[0].issue_id == "I_crash"
    assert stopped == ["stopped work on fix-crash"]
    assert WorkStore(root).active()[0] == []


def test_a_session_keeps_one_record_across_sandboxed_and_host_commands(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)
    start_issue_work(root, "build-observer", lookup=present(CLAUDE), environ={})

    messages = stop_issue_work(root, lookup=ISOLATED, environ=CLAUDE_ENVIRON)

    assert messages == ["stopped work on build-observer"]
    assert WorkStore(root).active()[0] == []


def test_a_record_without_a_hook_process_is_keyed_by_session_identity(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", None)

    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON)

    active, _ = WorkStore(root).active()
    assert active[0].session_process is None
    assert active[0].session_id == CODEX_SESSION
    assert active[0].session_key.startswith("codex-session-")
    assert CODEX_SESSION not in active[0].session_key
    assert active[0].session_label == f"codex session {CODEX_SESSION}"
    assert stop_issue_work(root, lookup=ISOLATED, environ=CODEX_ENVIRON) == [
        "stopped work on build-observer"
    ]


def test_legacy_record_is_adopted_by_the_same_session(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)
    start_issue_work(root, "build-observer", lookup=codex_lookup, environ={})
    legacy, _ = WorkStore(root).active()
    assert legacy[0].session_id is None

    messages = start_issue_work(
        root, "fix-crash", lookup=ISOLATED, environ=CODEX_ENVIRON
    )

    active, _ = WorkStore(root).active()
    assert "switched from build-observer to fix-crash" in messages[0]
    assert [work.session_key for work in active] == [legacy[0].session_key]
    assert active[0].session_id == CODEX_SESSION


@pytest.mark.parametrize(
    ("arrange", "environ", "expected"),
    [
        pytest.param(
            lambda root: None,
            CODEX_ENVIRON,
            "no lifecycle hook record for Codex session",
            id="missing",
        ),
        pytest.param(
            lambda root: hook_record(root, CODEX_SESSION, "claude-code", CLAUDE),
            CODEX_ENVIRON,
            "published by Claude Code",
            id="cross-harness",
        ),
        pytest.param(
            # A graceful SessionEnd removes the record; an ended record is a
            # legacy shape that still identifies no running session.
            lambda root: legacy_ended_record(root, CLAUDE_SESSION, "claude-code"),
            CLAUDE_ENVIRON,
            "is stale (ended)",
            id="ended",
        ),
        pytest.param(
            lambda root: hook_record(
                root,
                CLAUDE_SESSION,
                "claude-code",
                ProcessIdentity(4141, 1, "claude", "Tue Aug 25 02:00:00 2026"),
            ),
            CLAUDE_ENVIRON,
            "published for pid 4141",
            id="pid-mismatch",
        ),
        pytest.param(
            lambda root: (
                session_directory(root).mkdir(parents=True),
                (session_directory(root) / f"{CODEX_SESSION}.json").write_text(
                    "{not json"
                ),
            ),
            CODEX_ENVIRON,
            "cannot be read",
            id="unreadable",
        ),
    ],
)
def test_rejected_identities_fail_actionably_and_write_no_binding(
    tmp_path: Path,
    arrange: Callable[[Path], object],
    environ: dict[str, str],
    expected: str,
) -> None:
    root = repository(tmp_path / "repo")
    arrange(root)

    with pytest.raises(RuntimeError, match=re.escape(expected)):
        start_issue_work(root, "build-observer", lookup=ISOLATED, environ=environ)

    assert WorkStore(root).active()[0] == []
    with pytest.raises(RuntimeError, match=re.escape(expected)):
        stop_issue_work(root, lookup=ISOLATED, environ=environ)


def test_a_gone_session_record_is_stale_not_an_identity(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)

    with pytest.raises(RuntimeError, match="process is gone"):
        start_issue_work(root, "build-observer", lookup=absent(), environ=CODEX_ENVIRON)

    assert WorkStore(root).active()[0] == []


def test_coexisting_harness_identities_are_ambiguous_until_named(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)
    both = {**CODEX_ENVIRON, **CLAUDE_ENVIRON}

    with pytest.raises(RuntimeError, match="more than one live Agent Session"):
        start_issue_work(root, "build-observer", lookup=ISOLATED, environ=both)
    assert WorkStore(root).active()[0] == []

    named = {**both, SESSION_OVERRIDE_VARIABLE: f"codex:{CODEX_SESSION}"}
    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=named)

    active, _ = WorkStore(root).active()
    assert [work.harness for work in active] == ["codex"]
    assert active[0].session_id == CODEX_SESSION


def test_coexisting_harnesses_resolve_when_only_one_identity_is_live(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)
    both = {**CODEX_ENVIRON, **CLAUDE_ENVIRON}

    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=both)

    active, _ = WorkStore(root).active()
    assert [work.harness for work in active] == ["claude-code"]


def test_codex_and_claude_code_sandboxed_runs_on_one_issue_are_independent(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    hook_record(root, CODEX_SESSION, "codex", CODEX)
    hook_record(root, CLAUDE_SESSION, "claude-code", CLAUDE)

    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON)
    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CLAUDE_ENVIRON)

    active, _ = WorkStore(root).active()
    assert {work.harness for work in active} == {"codex", "claude-code"}
    assert len({work.session_key for work in active}) == 2
    assert stop_issue_work(root, lookup=ISOLATED, environ=CODEX_ENVIRON) == [
        "stopped work on build-observer"
    ]
    assert [work.harness for work in WorkStore(root).active()[0]] == ["claude-code"]


def test_override_must_name_a_supported_harness(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")

    with pytest.raises(RuntimeError, match=SESSION_OVERRIDE_VARIABLE):
        start_issue_work(
            root,
            "build-observer",
            lookup=ISOLATED,
            environ={SESSION_OVERRIDE_VARIABLE: "cursor:abc"},
        )


def test_claim_without_a_worktree_cannot_be_validated() -> None:
    with pytest.raises(RuntimeError, match="only be validated at a Worktree"):
        identify_agent_session(ISOLATED, environ=CODEX_ENVIRON)


# --- One active Agent Run per session across a Repository's Worktrees -------


def linked_worktree(root: Path, path: Path, branch: str) -> Path:
    """Commit the Project's configuration and Issues, then link a Worktree."""
    subprocess.run(["git", "add", ".dashpot", "issues"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-q",
            "-m",
            "seed",
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", branch, str(path)],
        cwd=root,
        check=True,
    )
    return path.resolve()


def two_worktrees(tmp_path: Path) -> tuple[Path, Path]:
    main = repository(tmp_path / "repo").resolve()
    linked = linked_worktree(main, tmp_path / "repo-linked", "linked")
    return main, linked


def target(worktree: Path) -> ObservationTarget:
    return ObservationTarget(
        path=str(worktree),
        head="abc123",
        branch="main",
        detached=False,
        dirty=False,
        availability="available",
        elapsed_ms=0,
        diagnostics=[],
        role="main",
    )


ROUTES = [
    pytest.param(codex_lookup, {}, id="process-route"),
    pytest.param(ISOLATED, CODEX_ENVIRON, id="sandboxed-claim"),
]


def test_codex_declares_where_its_active_run_will_resume(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]

    messages = relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)

    (pending,) = WorkStore(a).active()[0]
    assert messages == [
        f"prepared this Agent Run to resume at {b}; exit this Codex client "
        f"before resuming session {CODEX_SESSION} there"
    ]
    assert pending.run_id == before.run_id
    assert pending.started_at == before.started_at
    assert pending.relocation is not None
    assert pending.relocation.target_worktree == str(b)
    assert WorkStore(b).active()[0] == []


def test_relocation_requires_a_confirmed_codex_identity(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})

    with pytest.raises(RuntimeError, match="Agent Session Identity is not confirmed"):
        relocate_issue_work(a, b, lookup=codex_lookup, environ={})

    assert WorkStore(a).active()[0][0].relocation is None


def test_relocation_refuses_a_target_outside_the_linked_worktrees(
    tmp_path: Path,
) -> None:
    a, _b = two_worktrees(tmp_path)
    unrelated = repository(tmp_path / "unrelated")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)

    with pytest.raises(RuntimeError, match="not a linked Worktree"):
        relocate_issue_work(a, unrelated, lookup=codex_lookup, environ=CODEX_ENVIRON)

    assert WorkStore(a).active()[0][0].relocation is None


def test_relocation_refuses_unreadable_work_store_state(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    unreadable = WorkStore(b).record_path("other-session")
    unreadable.parent.mkdir(parents=True)
    unreadable.write_text("not json")

    with pytest.raises(DashpotError, match="repair the Work Store"):
        relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)

    assert WorkStore(a).active()[0][0].relocation is None


def test_session_end_keeps_a_declared_codex_relocation_pending(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]

    session_end(a, CODEX_SESSION, "codex", CODEX)

    (pending,) = WorkStore(a).active()[0]
    assert pending == before
    assert session_directory(a).joinpath(f"{CODEX_SESSION}.json").exists() is False


def test_relocation_records_an_identity_confirmed_after_work_started(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})
    assert WorkStore(a).active()[0][0].session_id is None

    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (pending,) = WorkStore(a).active()[0]
    assert pending.session_id == CODEX_SESSION

    session_end(a, CODEX_SESSION, "codex", CODEX)

    assert WorkStore(a).active()[0] == [pending]


def test_target_hook_completes_the_declared_relocation_as_the_same_run(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]
    session_end(a, CODEX_SESSION, "codex", CODEX)

    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    assert WorkStore(a).active()[0] == []
    (continued,) = WorkStore(b).active()[0]
    assert continued.run_id == before.run_id
    assert continued.started_at == before.started_at
    assert continued.issue_id == before.issue_id
    assert continued.relocation is None
    assert continued.session_process == SessionProcess(
        pid=resumed.pid, started_at=resumed.started_at
    )
    assert continued.working_directory == str(b)
    assert continued.branch == "linked"


def test_target_hook_repairs_the_persisted_two_record_crash_window(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (pending,) = WorkStore(a).active()[0]
    session_end(a, CODEX_SESSION, "codex", CODEX)
    WorkStore(b).start(
        replace(
            pending,
            session_label=f"codex pid {resumed.pid}",
            session_process=SessionProcess(
                pid=resumed.pid, started_at=resumed.started_at
            ),
            working_directory=str(b),
            branch="linked",
            relocation=None,
        )
    )

    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "UserPromptSubmit",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    assert WorkStore(a).active()[0] == []
    (continued,) = WorkStore(b).active()[0]
    assert continued.run_id == pending.run_id
    assert continued.relocation is None


def test_an_abandoned_relocation_remains_visible_and_actionable(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    session_end(a, CODEX_SESSION, "codex", CODEX)

    runs, diagnostics = observe_agent_runs(
        {"project:test": [target(a), target(b)]},
        state_directory(),
        lookup=absent(),
    )

    assert [(run.issue_id, run.state, run.started_at) for run in runs] == [
        ("I_observer", "unknown", WorkStore(a).active()[0][0].started_at)
    ]
    assert [item.code for item in diagnostics] == ["work-relocation-pending"]
    assert str(b) in diagnostics[0].message
    assert "work stop --session" in diagnostics[0].message
    assert "relocation pending" in show_issue_work(a)[0]


def test_a_resume_at_the_wrong_target_cannot_reassign_the_pending_run(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    c = (tmp_path / "repo-third").resolve()
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "third", str(c)],
        cwd=a,
        check=True,
    )
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    session_end(a, CODEX_SESSION, "codex", CODEX)
    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(c),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    with pytest.raises(RuntimeError, match=re.escape(f"prepared to resume at {b}")):
        start_issue_work(
            c,
            "build-observer",
            lookup=present(resumed),
            environ=CODEX_ENVIRON,
        )

    assert len(WorkStore(a).active()[0]) == 1
    assert WorkStore(b).active()[0] == []
    assert WorkStore(c).active()[0] == []
    _runs, diagnostics = observe_agent_runs(
        {"project:test": [target(a), target(b), target(c)]},
        state_directory(),
        lookup=table_lookup({resumed.pid: resumed}),
    )
    assert [item.code for item in diagnostics] == ["work-relocation-mismatched"]
    assert str(c) in diagnostics[0].message
    assert str(b) in diagnostics[0].message


def test_start_cannot_bypass_an_unreadable_pending_source(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    session_end(a, CODEX_SESSION, "codex", CODEX)
    (source_record,) = WorkStore(a).directory.glob("*.json")
    source_record.write_text("not json")
    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    with pytest.raises(DashpotError, match="Cannot read Work Store record"):
        start_issue_work(
            b,
            "build-observer",
            lookup=present(resumed),
            environ=CODEX_ENVIRON,
        )

    assert source_record.read_text() == "not json"
    assert WorkStore(b).active()[0] == []


def test_concurrent_codex_clients_cannot_complete_a_relocation(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    both_live = table_lookup({CODEX.pid: CODEX, resumed.pid: resumed})
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]

    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=both_live,
    )

    assert WorkStore(a).active()[0] == [before]
    assert WorkStore(b).active()[0] == []
    _runs, diagnostics = observe_agent_runs(
        {"project:test": [target(a), target(b)]},
        state_directory(),
        lookup=both_live,
    )
    assert [item.code for item in diagnostics] == ["work-relocation-concurrent"]
    assert str(a) in diagnostics[0].message
    assert str(b) in diagnostics[0].message

    session_end(a, CODEX_SESSION, "codex", CODEX)
    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "UserPromptSubmit",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0][0].run_id == before.run_id


def test_a_killed_old_client_can_resume_after_its_process_is_proved_gone(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]

    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0][0].run_id == before.run_id


def test_sandboxed_identity_route_preserves_the_run_across_resume(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]
    relocate_issue_work(a, b, lookup=ISOLATED, environ=CODEX_ENVIRON)
    session_end(a, CODEX_SESSION, "codex", CODEX)

    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(b),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0][0].run_id == before.run_id


def test_a_tool_call_at_another_worktree_cannot_prepare_relocation(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)

    with pytest.raises(RuntimeError, match=re.escape(f"not at {b}")):
        relocate_issue_work(b, a, lookup=codex_lookup, environ=CODEX_ENVIRON)

    (unchanged,) = WorkStore(a).active()[0]
    assert unchanged.relocation is None
    assert WorkStore(b).active()[0] == []


def test_claude_code_keeps_using_enter_worktree_instead_of_relocation_intent(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CLAUDE_SESSION, "claude-code", CLAUDE)
    start_issue_work(
        a, "build-observer", lookup=present(CLAUDE), environ=CLAUDE_ENVIRON
    )

    with pytest.raises(RuntimeError, match=r"Claude Code moves.*EnterWorktree"):
        relocate_issue_work(a, b, lookup=present(CLAUDE), environ=CLAUDE_ENVIRON)

    assert WorkStore(a).active()[0][0].relocation is None


def test_resuming_at_the_origin_can_cancel_a_failed_relocation(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    resumed = ProcessIdentity(5252, 1, "codex", "Sat Sep 05 05:20:00 2026")
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ=CODEX_ENVIRON)
    relocate_issue_work(a, b, lookup=codex_lookup, environ=CODEX_ENVIRON)
    (before,) = WorkStore(a).active()[0]
    session_end(a, CODEX_SESSION, "codex", CODEX)
    publish_hook_event(
        {
            "session_id": CODEX_SESSION,
            "cwd": str(a),
            "hook_event_name": "SessionStart",
        },
        environ={},
        process=resumed,
        harness="codex",
        lookup=table_lookup({resumed.pid: resumed}),
    )

    messages = relocate_issue_work(a, a, lookup=present(resumed), environ=CODEX_ENVIRON)

    (continued,) = WorkStore(a).active()[0]
    assert messages == ["cancelled the pending relocation; this Agent Run remains here"]
    assert continued.run_id == before.run_id
    assert continued.started_at == before.started_at
    assert continued.relocation is None
    assert continued.session_process == SessionProcess(
        pid=resumed.pid, started_at=resumed.started_at
    )


@pytest.mark.parametrize(("lookup", "environ"), ROUTES)
def test_start_after_a_verified_relocation_moves_the_run(
    tmp_path: Path, lookup: ProcessLookup, environ: dict[str, str]
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=EARLIER)
    start_issue_work(a, "build-observer", lookup=lookup, environ=environ)
    hook_record(b, CODEX_SESSION, "codex", CODEX, at=LATER)

    messages = start_issue_work(b, "fix-crash", lookup=lookup, environ=environ)

    assert messages == [
        f"switched from build-observer at {a} to fix-crash at {b} (I_crash)"
    ]
    assert WorkStore(a).active()[0] == []
    assert list(issue_ids(b).values()) == ["I_crash"]
    assert show_issue_work(a) == ["no active Issue work at this worktree"]
    assert len(show_issue_work(b)) == 1


@pytest.mark.parametrize(("lookup", "environ"), ROUTES)
def test_start_after_returning_from_a_worktree_moves_the_run_back(
    tmp_path: Path, lookup: ProcessLookup, environ: dict[str, str]
) -> None:
    """The return trip is a relocation too: ``ExitWorktree`` publishes from A."""
    a, b = two_worktrees(tmp_path)
    returned = "2026-08-30T03:41:00.000000Z"
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=EARLIER)
    start_issue_work(a, "build-observer", lookup=lookup, environ=environ)
    hook_record(b, CODEX_SESSION, "codex", CODEX, at=LATER)
    start_issue_work(b, "fix-crash", lookup=lookup, environ=environ)
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=returned)

    messages = start_issue_work(a, "build-observer", lookup=lookup, environ=environ)

    assert messages == [
        f"switched from fix-crash at {b} to build-observer at {a} (I_observer)"
    ]
    assert WorkStore(b).active()[0] == []
    assert list(issue_ids(a).values()) == ["I_observer"]


def test_start_where_the_session_is_not_is_refused(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})

    with pytest.raises(RuntimeError, match=re.escape(f"is at {a}")):
        start_issue_work(b, "fix-crash", lookup=codex_lookup, environ={})

    assert WorkStore(b).active()[0] == []
    assert list(issue_ids(a).values()) == ["I_observer"]


@pytest.mark.parametrize(("lookup", "environ"), ROUTES)
def test_a_stale_record_cannot_confirm_a_start_where_the_session_left(
    tmp_path: Path, lookup: ProcessLookup, environ: dict[str, str]
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=EARLIER)
    hook_record(b, CODEX_SESSION, "codex", CODEX, at=LATER)

    with pytest.raises(RuntimeError, match=re.escape(f"is at {b}")):
        start_issue_work(a, "build-observer", lookup=lookup, environ=environ)

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == []


def test_a_global_store_record_places_a_session_at_its_worktree(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX, store=state_directory())

    with pytest.raises(RuntimeError, match=re.escape(f"is at {a}")):
        start_issue_work(b, "fix-crash", lookup=codex_lookup, environ={})
    messages = start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})

    assert messages == ["started work on build-observer (I_observer)"]
    assert WorkStore(b).active()[0] == []


def test_stop_ends_the_run_wherever_in_the_repository_it_is(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})

    messages = stop_issue_work(b, lookup=codex_lookup, environ={})

    assert messages == [f"stopped work on build-observer at {a}"]
    assert WorkStore(a).active()[0] == []
    assert stop_issue_work(b, lookup=codex_lookup, environ={}) == [
        "no active Issue work for this session"
    ]


def test_without_hook_records_a_session_starts_where_it_runs(tmp_path: Path) -> None:
    a, b = two_worktrees(tmp_path)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})

    messages = start_issue_work(b, "fix-crash", lookup=codex_lookup, environ={})

    assert messages == ["started work on fix-crash (I_crash)"]
    assert list(issue_ids(a).values()) == ["I_observer"]
    assert list(issue_ids(b).values()) == ["I_crash"]


def test_a_relocated_session_is_observed_once_without_conflict(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    hook_record(a, CODEX_SESSION, "codex", CODEX, at=EARLIER)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})
    hook_record(b, CODEX_SESSION, "codex", CODEX, at=LATER)
    start_issue_work(b, "build-observer", lookup=codex_lookup, environ={})

    runs, diagnostics = observe_agent_runs(
        {"project:test": [target(a), target(b)]},
        state_directory(),
        lookup=codex_lookup,
    )

    assert [(run.observation_target, run.issue_id) for run in runs] == [
        (str(b), "I_observer")
    ]
    assert "work-session-conflict" not in {item.code for item in diagnostics}


# --- A graceful SessionEnd ends the session's Agent Run (ADR 0015) -----------


def session_end(
    root: Path, session_id: str, harness: str, process: ProcessIdentity
) -> None:
    """Publish the session's SessionEnd from ``root`` as its harness would."""
    publish_hook_event(
        {"session_id": session_id, "cwd": str(root), "hook_event_name": "SessionEnd"},
        environ={},
        process=process,
        harness=harness,
    )


def test_session_end_ends_the_sessions_run(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo").resolve()
    hook_record(root, CODEX_SESSION, "codex", CODEX)
    start_issue_work(root, "build-observer", lookup=codex_lookup, environ={})

    session_end(root, CODEX_SESSION, "codex", CODEX)

    assert WorkStore(root).active() == ([], [])
    assert session_directory(root).joinpath(f"{CODEX_SESSION}.json").exists() is False
    runs, diagnostics = observe_agent_runs(
        {"project:example": [target(root)]}, tmp_path / "global-state", lookup=absent()
    )
    assert runs == []
    assert [d.code for d in diagnostics] == []


def test_session_end_ends_the_run_wherever_in_the_repository_it_is(
    tmp_path: Path,
) -> None:
    a, b = two_worktrees(tmp_path)
    start_issue_work(a, "build-observer", lookup=codex_lookup, environ={})

    session_end(b, CODEX_SESSION, "codex", CODEX)

    assert WorkStore(a).active()[0] == []
    assert WorkStore(b).active()[0] == []


def test_session_end_leaves_other_sessions_runs_alone(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo").resolve()
    start_issue_work(root, "build-observer", lookup=codex_lookup, environ={})
    start_issue_work(root, "fix-crash", lookup=present(CLAUDE), environ={})

    session_end(root, CODEX_SESSION, "codex", CODEX)

    assert list(issue_ids(root).values()) == ["I_crash"]


def test_session_end_ends_a_run_opted_in_by_agent_session_identity(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo").resolve()
    hook_record(root, CODEX_SESSION, "codex", CODEX)
    start_issue_work(root, "build-observer", lookup=ISOLATED, environ=CODEX_ENVIRON)
    (work,) = WorkStore(root).active()[0]
    assert work.session_id == CODEX_SESSION

    # The hook runs on the host, so it sees the process the sandbox could not.
    session_end(root, CODEX_SESSION, "codex", CODEX)

    assert WorkStore(root).active() == ([], [])


def test_session_end_outside_any_repository_reconciles_nothing(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo").resolve()
    start_issue_work(root, "build-observer", lookup=codex_lookup, environ={})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    session_end(elsewhere, CODEX_SESSION, "codex", CODEX)

    assert list(issue_ids(root).values()) == ["I_observer"]
