from __future__ import annotations

from typing import cast

import pytest

from dashpot.core.model import Harness, harness_alternatives
from dashpot.sessions.harnesses import (
    ADAPTERS,
    CLAUDE_CODE,
    CODEX,
    OPENCODE,
    SESSION_OVERRIDE_VARIABLE,
    HarnessError,
    SessionIdentityClaim,
    adapter,
    is_child_scoped,
    locates_session,
    native_claims,
    override_claim,
)
from dashpot.sessions.processes import ProcessIdentity

STARTED = "Tue Aug 25 01:00:00 2026"


def test_each_supported_harness_has_one_adapter() -> None:
    assert set(ADAPTERS) == {"codex", "claude-code", "opencode"}
    assert adapter("codex") is CODEX
    assert adapter("claude-code") is CLAUDE_CODE
    assert adapter("opencode") is OPENCODE
    assert harness_alternatives() == "Codex, Claude Code, or OpenCode"
    with pytest.raises(HarnessError, match="unsupported harness"):
        adapter(cast("Harness", "cursor"))


def test_codex_adapter_never_treats_the_sandbox_helper_as_the_host() -> None:
    helper = ProcessIdentity(
        10, 20, "codex", STARTED, "codex-linux-sandbox --sandbox-policy-cwd /repo"
    )
    host = ProcessIdentity(20, 1, "codex", STARTED, "/usr/bin/codex")
    bwrap = ProcessIdentity(30, 1, "bwrap", STARTED, "bwrap --unshare-pid sh")

    assert CODEX.is_host_process(helper) is False
    assert CODEX.is_host_process(host) is True
    assert CLAUDE_CODE.is_host_process(bwrap) is False
    assert CLAUDE_CODE.is_host_process(ProcessIdentity(40, 1, "claude", STARTED))


VERSIONS = "/home/person/.local/share/claude/versions"
SESSION = "8730ba65-e1a8-4318-a083-a66c5e615b86"
DAEMON = "/tmp/cc-daemon-1000/b4bd083d"


# Argument vectors as ``ps`` reported them for the supervisor's processes on
# Linux (docs/spikes/measurements/issue-326-claude-trace.jsonl, and
# issue-160-claude-trace.jsonl at 2.1.276).
@pytest.mark.parametrize(
    ("command", "arguments", "host"),
    [
        pytest.param(
            "2.1.285",
            f"{VERSIONS}/2.1.285 --session-id {SESSION} fix it --name a",
            True,
            id="worker-spawned-for-its-session",
        ),
        pytest.param(
            "2.1.285",
            f"{VERSIONS}/2.1.285 --resume /config/projects/-r/{SESSION}.jsonl --name a",
            True,
            id="worker-resumed-after-a-crash",
        ),
        pytest.param(
            "2.1.276",
            f"claude bg-spare --bg-spare {DAEMON}/spare/cc5d327e.claim.sock",
            True,
            id="worker-claimed-from-a-spare",
        ),
        pytest.param(
            "2.1.285",
            f"/Users/A Person/.local/share/claude/versions/2.1.285 --session-id {SESSION}",
            True,
            id="worker-under-a-home-with-a-space",
        ),
        pytest.param(
            f"{VERSIONS}/2.1.285",
            f"{VERSIONS}/2.1.285 --session-id {SESSION} fix it",
            True,
            id="comm-given-as-the-executable-path",
        ),
        pytest.param(
            "2.1.285",
            f"{VERSIONS}/2.1.285 daemon run --origin transient --spawned-by {{}}",
            False,
            id="supervisor",
        ),
        pytest.param(
            "2.1.285",
            f"claude bg-pty-host --bg-pty-host {DAEMON}/pty/8730ba65.sock 200 50 -- "
            f"{VERSIONS}/2.1.285 --session-id {SESSION}",
            False,
            id="pty-host-carrying-its-workers-command",
        ),
        pytest.param(
            "2.1.285", f"{VERSIONS}/2.1.285 agents", False, id="agents-client"
        ),
        pytest.param(
            "2.1.285", f"{VERSIONS}/2.1.285 attach 8730ba65", False, id="attach-client"
        ),
        pytest.param(
            "2.1.283",
            "/opt/pin/claude/versions/2.1.283 --model m --agents {}",
            False,
            id="versioned-executable-without-a-worker-shape",
        ),
        pytest.param(
            "2.1.285",
            f"{VERSIONS}/2.1.284 --session-id {SESSION}",
            False,
            id="executable-of-another-version",
        ),
        pytest.param(
            "1.4.2",
            f"/opt/sync/1.4.2 --session-id {SESSION}",
            False,
            id="unrelated-version-named-process",
        ),
        pytest.param("2.1.285", None, False, id="version-name-alone"),
        pytest.param(
            "node",
            f"claude bg-spare --bg-spare {DAEMON}/spare/cc5d327e.claim.sock",
            False,
            id="worker-shape-without-a-version-name",
        ),
    ],
)
def test_claude_code_adapter_locates_a_supervised_worker_by_its_arguments(
    command: str, arguments: str | None, host: bool
) -> None:
    process = ProcessIdentity(50, 40, command, STARTED, arguments)

    assert CLAUDE_CODE.is_host_process(process) is host
    assert CODEX.is_host_process(process) is False


def test_codex_adapter_claims_the_thread_identity_its_hooks_publish() -> None:
    assert CODEX.claim_session_identity({}) is None
    assert CODEX.claim_session_identity({"CODEX_THREAD_ID": "not valid!"}) is None
    claim = CODEX.claim_session_identity({"CODEX_THREAD_ID": "01a0-thread"})
    assert claim == SessionIdentityClaim("codex", "01a0-thread", "Codex environment")


def test_claude_code_adapter_claims_session_identity_with_its_host_pid() -> None:
    assert CLAUDE_CODE.claim_session_identity({"CLAUDE_PID": "7"}) is None
    claim = CLAUDE_CODE.claim_session_identity(
        {"CLAUDE_CODE_SESSION_ID": "01c7-session", "CLAUDE_PID": "63792"}
    )
    assert claim == SessionIdentityClaim(
        "claude-code", "01c7-session", "Claude Code environment", 63792
    )
    without_pid = CLAUDE_CODE.claim_session_identity(
        {"CLAUDE_CODE_SESSION_ID": "01c7-session", "CLAUDE_PID": "n/a"}
    )
    assert without_pid is not None
    assert without_pid.pid is None


def test_opencode_adapter_hosts_only_the_opencode_backend() -> None:
    backend = ProcessIdentity(
        4100, 1, "opencode", STARTED, "/home/person/.opencode/bin/opencode serve"
    )
    command = ProcessIdentity(4200, 4100, "MainThread", STARTED, "node build.mjs")

    assert OPENCODE.is_host_process(backend) is True
    assert OPENCODE.is_host_process(command) is False
    assert OPENCODE.exclusive_session_process is False


def test_opencode_adapter_claims_only_a_complete_corroborated_identity() -> None:
    complete = {
        "DASHPOT_OPENCODE_SESSION_ID": "ses_01root",
        "DASHPOT_OPENCODE_GENERATION": "gen-1",
        "DASHPOT_OPENCODE_PID": "4100",
    }

    assert OPENCODE.claim_session_identity(complete) == SessionIdentityClaim(
        "opencode", "ses_01root", "OpenCode plugin", 4100, "gen-1"
    )
    for variable, value in (
        ("DASHPOT_OPENCODE_SESSION_ID", ""),
        ("DASHPOT_OPENCODE_GENERATION", "not a generation!"),
        ("DASHPOT_OPENCODE_PID", "n/a"),
    ):
        assert OPENCODE.claim_session_identity({**complete, variable: value}) is None


def test_native_claims_report_every_harness_present_in_adapter_order() -> None:
    environ = {"CLAUDE_CODE_SESSION_ID": "cc", "CODEX_THREAD_ID": "cx"}

    claims = native_claims(environ)

    assert [claim.harness for claim in claims] == ["codex", "claude-code"]
    assert native_claims({}) == []


def test_override_claim_is_explicit_and_validated_in_shape() -> None:
    assert override_claim({}) is None
    claim = override_claim({SESSION_OVERRIDE_VARIABLE: "claude-code:01c7-session"})
    assert claim == SessionIdentityClaim(
        "claude-code", "01c7-session", SESSION_OVERRIDE_VARIABLE
    )
    for raw in ("01c7-session", "cursor:abc", "codex:", "codex:bad value"):
        with pytest.raises(HarnessError, match=SESSION_OVERRIDE_VARIABLE):
            override_claim({SESSION_OVERRIDE_VARIABLE: raw})


@pytest.mark.parametrize(
    ("harness", "event", "locates"),
    [
        ("codex", {"hook_event_name": "UserPromptSubmit"}, True),
        ("codex", {"hook_event_name": "UserPromptSubmit", "agent_id": "child"}, False),
        ("codex", {"hook_event_name": "Stop"}, False),
        ("codex", {"hook_event_name": "SessionStart"}, False),
        ("codex", {"hook_event_name": "SessionEnd"}, False),
        (
            "claude-code",
            {"hook_event_name": "PostToolUse", "tool_name": "EnterWorktree"},
            True,
        ),
        (
            "claude-code",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "ExitWorktree",
                "tool_input": {"action": "keep"},
            },
            True,
        ),
        # ``remove`` deletes the Worktree it leaves; it is not a move.
        (
            "claude-code",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "ExitWorktree",
                "tool_input": {"action": "remove"},
            },
            False,
        ),
        (
            "claude-code",
            {"hook_event_name": "PostToolUse", "tool_name": "ExitWorktree"},
            False,
        ),
        (
            "claude-code",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "ExitWorktree",
                "tool_input": "keep",
            },
            False,
        ),
        (
            "claude-code",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "EnterWorktree",
                "agent_id": "child",
            },
            False,
        ),
        # A persistent shell ``cd`` moves every later hook's ``cwd``.
        ("claude-code", {"hook_event_name": "PostToolUse", "tool_name": "Bash"}, False),
        (
            "claude-code",
            {"hook_event_name": "PreToolUse", "tool_name": "EnterWorktree"},
            False,
        ),
        ("claude-code", {"hook_event_name": "UserPromptSubmit"}, False),
        ("claude-code", {"hook_event_name": "Stop"}, False),
        ("claude-code", {"hook_event_name": "SessionStart"}, False),
        (
            "codex",
            {"hook_event_name": "PostToolUse", "tool_name": "EnterWorktree"},
            False,
        ),
    ],
)
def test_only_designated_session_scoped_evidence_locates_a_session(
    harness: Harness, event: dict[str, object], locates: bool
) -> None:
    assert locates_session(harness, event) is locates


def test_an_event_naming_a_delegate_is_child_scoped() -> None:
    assert is_child_scoped({"agent_id": "a686b12"}) is True
    assert is_child_scoped({"agent_id": ""}) is False
    assert is_child_scoped({"agent_id": 7}) is False
    assert is_child_scoped({}) is False
