"""The independent verifier rejects broken or overstated push transport evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

CHECKOUT = Path(__file__).resolve().parents[1]
TRACE = CHECKOUT / "docs/spikes/measurements/issue-684-codex-trace.jsonl"
VERIFIER = CHECKOUT / "scripts/experiments/codex-684/verify.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")


def verify(
    records: list[dict[str, Any]], tmp_path: Path, *, wrong_binary: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run the public verifier with isolated bytes for its binary digest check."""
    binary = tmp_path / "binary-digest-fixture"
    binary.write_bytes(b"Verifier integrity fixture, never executed.\n")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    records[0]["binarySHA256"] = "0" * 64 if wrong_binary else digest
    trace = tmp_path / "trace.jsonl"
    trace.write_text("".join(json.dumps(row) + "\n" for row in records))
    return subprocess.run(
        ["node", str(VERIFIER), str(trace), str(binary)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def rows() -> list[dict[str, Any]]:
    """The retained real observations, isolated before each mutation."""
    return [json.loads(line) for line in TRACE.read_text().splitlines()]


def first(records: list[dict[str, Any]], kind: str, **fields: object) -> dict[str, Any]:
    """The first record of a kind whose top-level fields match."""
    return next(
        row
        for row in records
        if row["kind"] == kind and all(row.get(k) == v for k, v in fields.items())
    )


def step(records: list[dict[str, Any]], scenario: str, name: str) -> dict[str, Any]:
    """The first report of one Worker step in one scenario."""
    return next(
        row["report"]
        for row in records
        if row["kind"] == "step"
        and row["scenario"] == scenario
        and row["report"]["step"] == name
    )


def test_retained_push_observations_verify(tmp_path: Path) -> None:
    result = verify(rows(), tmp_path)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["version"] == "codex-cli 0.166.0"
    assert "F9 reproduces inside the sandbox" in summary["checks"]


@pytest.mark.parametrize(
    ("mutation", "claim"),
    [
        pytest.param("source_identity", "source identity", id="source_identity"),
        pytest.param(
            "uncommitted_sources", "source identity", id="uncommitted_sources"
        ),
        pytest.param(
            "token_leak", "no credential or operator path in the trace", id="token_leak"
        ),
        pytest.param(
            "additional_write_root",
            "every lead and Worker ran workspace-write",
            id="additional_write_root",
        ),
        pytest.param(
            "foreign_worker",
            "every lead and Worker ran workspace-write",
            id="foreign_worker",
        ),
        pytest.param("f9_absent", "F9 reproduces inside the sandbox", id="f9_absent"),
        pytest.param(
            "remote_rewritten",
            "the remote URL stayed the scp-like SSH URL",
            id="remote_rewritten",
        ),
        pytest.param("https_unchallenged", "HTTPS remedy", id="https_unchallenged"),
        pytest.param("missing_receive", "SSH -F remedy", id="missing_receive"),
        pytest.param("stale_lease_accepted", "HTTPS remedy", id="stale_lease_accepted"),
        pytest.param(
            "hook_claimed_unsandboxed", "SSH -F remedy", id="hook_claimed_unsandboxed"
        ),
        pytest.param("known_host_written", "SSH -F remedy", id="known_host_written"),
        pytest.param(
            "approval_under_never",
            "escalation remedy under never",
            id="approval_under_never",
        ),
        pytest.param(
            "lead_approved", "escalation remedy under on-request", id="lead_approved"
        ),
        pytest.param("wrong_binary", "pinned release", id="wrong_binary"),
        pytest.param(
            "harness_ancestor", "detached from every harness", id="harness_ancestor"
        ),
        pytest.param(
            "home_path", "no credential or operator path in the trace", id="home_path"
        ),
        pytest.param(
            "shared_daemon_changed",
            "completed without failure",
            id="shared_daemon_changed",
        ),
        pytest.param(
            "never_ran_escalation",
            "escalation remedy under never",
            id="never_ran_escalation",
        ),
        pytest.param(
            "agent_directory_writable", "SSH -F remedy", id="agent_directory_writable"
        ),
        pytest.param(
            "known_hosts_unseeded", "SSH -F remedy", id="known_hosts_unseeded"
        ),
    ],
)
def test_push_verifier_refuses_overstated_evidence(
    mutation: str, claim: str, tmp_path: Path
) -> None:
    """Each overstated result fails the check that names that result."""
    records = rows()
    if mutation == "source_identity":
        records[0]["sourceSHA256"]["step.mjs"] = "0" * 64
    elif mutation == "uncommitted_sources":
        records[0]["checkout"]["experimentDirty"] = True
    elif mutation == "token_leak":
        records[-1]["tokenAbsent"] = False
    elif mutation == "additional_write_root":
        thread = first(records, "rollouts")["threads"][1]
        thread["turns"][0]["sandbox_policy"]["writable_roots"].append("/")
    elif mutation == "foreign_worker":
        thread = first(records, "rollouts")["threads"][1]
        thread["source"]["subagent"]["thread_spawn"]["parent_thread_id"] = "elsewhere"
    elif mutation == "f9_absent":
        probe = step(records, "escalated-never", "probe")
        probe["sshThroughSystem"] = {**probe["sshThroughSystem"], "status": 0}
    elif mutation == "remote_rewritten":
        first(records, "scenario.outcome", name="https")["remoteUrlUnchanged"] = False
    elif mutation == "https_unchallenged":
        first(records, "remote.request", scenario="https")["status"] = 200
    elif mutation == "missing_receive":
        first(records, "scenario.outcome", name="ssh-config")["remote"][
            "receives"
        ].pop()
    elif mutation == "stale_lease_accepted":
        step(records, "https", "stale-lease")["status"] = 0
    elif mutation == "hook_claimed_unsandboxed":
        step(records, "ssh-config", "push")["prepush"][0]["outsideWrite"] = {"ok": True}
    elif mutation == "known_host_written":
        step(records, "ssh-config", "unknown-host")["knownHostsWritten"] = True
    elif mutation == "approval_under_never":
        first(records, "approval")["scenario"] = "escalated-never"
    elif mutation == "lead_approved":
        lead = first(records, "scenario.outcome", name="escalated-approved")["lead"]
        first(records, "approval")["thread"] = lead
    elif mutation == "wrong_binary":
        pass
    elif mutation == "harness_ancestor":
        records[0]["runnerParent"] = 4242
        records[0]["ancestry"] = [{"pid": 4242, "comm": "claude", "harness": True}]
    elif mutation == "home_path":
        first(records, "scenario", name="https")["note"] = "/home/someone/.ssh"
    elif mutation == "shared_daemon_changed":
        first(records, "shared-daemon-dir")["removed"] = 1
    elif mutation == "never_ran_escalation":
        outcome = first(records, "scenario.outcome", name="escalated-never")
        outcome["workerOutputs"][1] = "Process exited with code 0"
    elif mutation == "agent_directory_writable":
        step(records, "ssh-config", "probe")["agent"]["directoryWrite"] = {"ok": True}
    elif mutation == "known_hosts_unseeded":
        step(records, "ssh-config", "probe")["sshCommand"]["knownHostsSeeded"] = False
    else:
        raise AssertionError(f"unknown mutation {mutation}")
    result = verify(records, tmp_path, wrong_binary=mutation == "wrong_binary")
    assert result.returncode != 0
    assert f"AssertionError [ERR_ASSERTION]: [{claim}" in result.stderr
