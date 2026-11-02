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
    records: list[dict[str, Any]], tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    """Run the public verifier with isolated bytes for its binary digest check."""
    binary = tmp_path / "binary-digest-fixture"
    binary.write_bytes(b"Verifier integrity fixture, never executed.\n")
    records[0]["binarySHA256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
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
    "mutation",
    [
        "source_identity",
        "uncommitted_sources",
        "token_leak",
        "additional_write_root",
        "foreign_worker",
        "f9_absent",
        "remote_rewritten",
        "https_unchallenged",
        "missing_receive",
        "stale_lease_accepted",
        "hook_claimed_unsandboxed",
        "known_host_written",
        "approval_under_never",
        "lead_approved",
    ],
)
def test_push_verifier_refuses_overstated_evidence(
    mutation: str, tmp_path: Path
) -> None:
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
    else:
        lead = first(records, "scenario.outcome", name="escalated-approved")["lead"]
        first(records, "approval")["thread"] = lead
    result = verify(records, tmp_path)
    assert result.returncode != 0
    assert "AssertionError" in result.stderr
