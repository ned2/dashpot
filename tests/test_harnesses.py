from __future__ import annotations

import pytest

from dashpot.harnesses import (
    ADAPTERS,
    CLAUDE_CODE,
    CODEX,
    SESSION_OVERRIDE_VARIABLE,
    SessionIdentityClaim,
    adapter,
    native_claims,
    override_claim,
)
from dashpot.processes import ProcessIdentity

STARTED = "Tue Aug 25 01:00:00 2026"


def test_each_supported_harness_has_one_adapter() -> None:
    assert set(ADAPTERS) == {"codex", "claude-code"}
    assert adapter("codex") is CODEX
    assert adapter("claude-code") is CLAUDE_CODE
    with pytest.raises(RuntimeError, match="unsupported harness"):
        adapter("cursor")


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
        with pytest.raises(RuntimeError, match=SESSION_OVERRIDE_VARIABLE):
            override_claim({SESSION_OVERRIDE_VARIABLE: raw})
