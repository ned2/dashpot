"""The independent verifier rejects broken or overstated permission evidence."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

CHECKOUT = Path(__file__).resolve().parents[1]
TRACE = CHECKOUT / "docs/spikes/measurements/issue-665-codex-trace.jsonl.gz"
VERIFIER = CHECKOUT / "scripts/experiments/codex-639/permissions-verify.mjs"
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
    return [
        json.loads(line) for line in gzip.decompress(TRACE.read_bytes()).splitlines()
    ]


def rewrite_probe(value: object, label: str, field: str) -> object:
    """Forge consistent raw and summarized successes to test semantic checks."""
    if isinstance(value, dict):
        rewritten = {
            key: rewrite_probe(item, label, field) for key, item in value.items()
        }
        if rewritten.get("label") == label and field in rewritten:
            rewritten[field] = {"ok": True}
        return rewritten
    if isinstance(value, list):
        return [rewrite_probe(item, label, field) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            match = re.search(r"PROBE (\{[^\n]*\})", value)
            if match:
                report = json.loads(match[1])
                if report["label"] == label:
                    report[field] = {"ok": True}
                    return (
                        value[: match.start(1)]
                        + json.dumps(report)
                        + value[match.end(1) :]
                    )
        else:
            return json.dumps(rewrite_probe(decoded, label, field))
    return value


def test_retained_permission_observations_verify(tmp_path: Path) -> None:
    result = verify(rows(), tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["workspaceReconnect"] == (
        "approval preserved; sandbox override omitted"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "source_identity",
        "omitted_source_identity",
        "additional_write_root",
        "missing_wait",
        "approved_read_denial",
        "same_turn",
        "session_grant",
        "borrowed_grant",
        "missing_guardian_guidance",
        "fabricated_subagent_stop",
        "cleared_stale_activity",
        "missing_allow_rule",
    ],
)
def test_permission_verifier_refuses_overstated_evidence(
    mutation: str, tmp_path: Path
) -> None:
    records = rows()
    if mutation == "source_identity":
        records[0]["sourceSHA256"]["permissions-run.mjs"] = "0" * 64
    elif mutation == "omitted_source_identity":
        records[0]["sourceSHA256"] = {}
        records[0]["dashpotSHA256"] = {}
    elif mutation == "additional_write_root":
        for thread in next(r for r in records if r["kind"] == "rollouts")["threads"]:
            for turn in thread["turns"]:
                turn["permission_profile"]["file_system"]["entries"].append(
                    {"path": {"type": "path", "path": "/home/ned"}, "access": "write"}
                )
    elif mutation == "missing_wait":
        row = next(
            r
            for r in records
            if r["kind"] == "model.request"
            and r["label"] == "lead-waiting-approve"
            and r["action"] == "wait_agent"
        )
        row["action"] = "exec_command"
    elif mutation in {"approved_read_denial", "borrowed_grant"}:
        label = (
            "worker-waiting-approve"
            if mutation == "approved_read_denial"
            else "background-after"
        )
        field = "deniedRead" if mutation == "approved_read_denial" else "laterWrite"
        records = cast("list[dict[str, Any]]", rewrite_probe(records, label, field))
    elif mutation == "same_turn":
        row = next(r for r in records if r["kind"] == "background.outcome")
        row["nextTurn"] = row["firstTurn"]
    elif mutation == "session_grant":
        next(r for r in records if r["kind"] == "permission.grant")["scope"] = "session"
    elif mutation == "missing_guardian_guidance":
        row = next(
            r
            for r in reversed(records)
            if r["kind"] == "model.request"
            and r["label"] == "lead-guardian-strict"
            and not r["side"]
        )
        row["messages"][0]["content"][0]["text"] = (
            "Agent interrupted by Guardian: 3 consecutive"
        )
    elif mutation == "fabricated_subagent_stop":
        row = next(
            r
            for r in records
            if r["kind"] == "observation" and r["label"] == "ordinary-interrupt"
        )
        hook = copy.deepcopy(next(r for r in records if r["kind"] == "hook"))
        hook["event"] = "SubagentStop"
        hook["payload"]["session_id"] = row["lead"]
        records.insert(-1, hook)
        for index, record in enumerate(records):
            record["receipt"] = index + 1
            record["receiptTime"] = index
    elif mutation == "cleared_stale_activity":
        observation = next(
            r
            for r in records
            if r["kind"] == "observation" and r["label"] == "guardian-strict"
        )
        observation["snapshot"]["result"]["agentRuns"][0]["workers"][0]["state"] = None
    else:
        next(r for r in records if r["kind"] == "command-allow-rule")["kind"] = (
            "omitted"
        )
    result = verify(records, tmp_path)
    assert result.returncode != 0
    assert "AssertionError" in result.stderr
