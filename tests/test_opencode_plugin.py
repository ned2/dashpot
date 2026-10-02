"""The managed OpenCode plugin's own bounds, driven in Node.js against a stub helper.

The helper's decisions are tested in ``test_opencode``; these tests hold the
plugin to what ADR 0078 bounds: a command's claim only from its own
acknowledged bootstrap, the shell budget, and the per-session queue and
helper limits.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dashpot.sessions.integrate import render_plugin

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")

# Answers like the helper: registration is accepted, a bootstrap is acknowledged
# with its command's claim, and a status is accepted after STUB_DELAY_MS. Each
# invocation is logged so a test can count what the plugin admitted.
STUB = """#!/usr/bin/env node
import { appendFileSync } from "node:fs";
let input = "";
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const request = JSON.parse(input);
  appendFileSync(process.env.STUB_LOG, JSON.stringify(request) + "\\n");
  if (request.kind === "bootstrap" && process.env.STUB_HANG === "bootstrap") {
    setTimeout(() => {}, 60000);
    return;
  }
  const answer =
    request.kind === "bootstrap"
      ? {
          result: "accepted",
          command: request.command,
          claim: { sessionID: request.session.id, generation: request.generation, pid: request.pid },
        }
      : { result: "accepted" };
  // Answer as if for another command, session, generation or backend.
  const mismatch = request.kind === "bootstrap" && process.env.STUB_MISMATCH;
  if (mismatch === "command") answer.command = "call_other";
  if (mismatch && mismatch !== "command") answer.claim[mismatch] = "other";
  setTimeout(() => console.log(JSON.stringify(answer)), Number(process.env.STUB_DELAY_MS ?? 0));
});
"""

DRIVER = """
const { DashpotOpenCodeObservation } = await import(process.argv[2]);
const client = {
  session: {
    get: async ({ path }) => ({ data: { id: path.id, directory: process.cwd(), parentID: null } }),
  },
};
const hooks = await DashpotOpenCodeObservation({ directory: process.cwd(), client });
const scenario = process.argv[3];
const result = {};
const shell = async (input, inherited = {}) => {
  const output = { env: { ...inherited } };
  const started = Date.now();
  await hooks["shell.env"](input, output);
  return { env: output.env, elapsed: Date.now() - started };
};
if (scenario === "claims") {
  result.pty = await shell({}, { DASHPOT_OPENCODE_SESSION_ID: "ses_outer", CODEX_THREAD_ID: "t" });
  result.tool = await shell({ sessionID: "ses_root", callID: "call_1" }, { CLAUDE_PID: "7" });
} else if (scenario === "budget") {
  result.tool = await shell({ sessionID: "ses_root", callID: "call_1" });
} else if (scenario === "queue") {
  const pending = [];
  for (let step = 0; step < 20; step++) {
    const type = step % 2 ? "idle" : "busy";
    pending.push(hooks.event({ event: { type: "session.status", properties: { sessionID: "ses_root", status: { type } } } }));
  }
  await Promise.all(pending);
} else if (scenario === "helpers") {
  for (let session = 0; session < 10; session++) {
    hooks.event({ event: { type: "session.status", properties: { sessionID: `ses_${session}`, status: { type: "busy" } } } });
  }
}
await hooks.dispose();
console.log(JSON.stringify(result));
"""


def drive(
    tmp_path: Path, scenario: str, **stub: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one scenario; answer its result and the helper requests in order."""
    helper = tmp_path / "helper.mjs"
    helper.write_text(STUB)
    helper.chmod(0o755)
    plugin = tmp_path / "dashpot.mjs"
    plugin.write_text(render_plugin(helper))
    driver = tmp_path / "driver.mjs"
    driver.write_text(DRIVER)
    log = tmp_path / "requests.jsonl"
    completed = subprocess.run(
        ["node", str(driver), plugin.as_uri(), scenario],
        cwd=tmp_path,
        env={
            "PATH": str(Path(shutil.which("node") or "node").parent),
            "STUB_LOG": str(log),
            **stub,
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    requests = [json.loads(line) for line in log.read_text().splitlines()]
    return json.loads(completed.stdout.strip().splitlines()[-1]), requests


def kinds(requests: list[dict[str, Any]]) -> list[str]:
    return [request["kind"] for request in requests]


def test_a_command_gets_a_claim_only_from_its_own_acknowledged_bootstrap(
    tmp_path: Path,
) -> None:
    result, requests = drive(tmp_path, "claims")

    # A PTY command names no session: it inherits no claim, its own or another
    # harness's, and is told why.
    assert result["pty"]["env"] == {
        "DASHPOT_OPENCODE_SESSION_ID": "",
        "DASHPOT_OPENCODE_GENERATION": "",
        "DASHPOT_OPENCODE_PID": "",
        "DASHPOT_AGENT_SESSION": "",
        "CODEX_THREAD_ID": "",
        "CLAUDE_CODE_SESSION_ID": "",
        "CLAUDE_PID": "",
        "DASHPOT_OPENCODE_UNCORROBORATED": "no-session-identity",
    }
    (bootstrap,) = [request for request in requests if request["kind"] == "bootstrap"]
    assert bootstrap["command"] == "call_1"
    env = result["tool"]["env"]
    assert env["DASHPOT_OPENCODE_SESSION_ID"] == "ses_root"
    assert env["DASHPOT_OPENCODE_GENERATION"] == bootstrap["generation"]
    assert env["DASHPOT_OPENCODE_PID"] == str(bootstrap["pid"])
    assert env["CLAUDE_PID"] == ""
    assert "DASHPOT_OPENCODE_UNCORROBORATED" not in env
    assert kinds(requests) == ["register", "bootstrap", "retire"]


@pytest.mark.parametrize("mismatch", ["command", "sessionID", "generation", "pid"])
def test_an_acknowledgment_for_anything_else_gives_no_claim(
    tmp_path: Path, mismatch: str
) -> None:
    result, _requests = drive(tmp_path, "claims", STUB_MISMATCH=mismatch)

    env = result["tool"]["env"]
    assert env["DASHPOT_OPENCODE_SESSION_ID"] == ""
    assert env["DASHPOT_OPENCODE_GENERATION"] == ""
    assert env["DASHPOT_OPENCODE_PID"] == ""
    assert env["DASHPOT_OPENCODE_UNCORROBORATED"] == "no-acknowledgment"


def test_a_command_waits_no_longer_than_its_shell_budget(tmp_path: Path) -> None:
    result, requests = drive(tmp_path, "budget", STUB_HANG="bootstrap")

    tool = result["tool"]
    assert tool["env"]["DASHPOT_OPENCODE_UNCORROBORATED"] == "no-acknowledgment"
    assert tool["env"]["DASHPOT_OPENCODE_SESSION_ID"] == ""
    assert 2900 <= tool["elapsed"] < 4500
    assert kinds(requests) == ["register", "bootstrap", "retire"]


def test_a_sessions_queue_admits_at_most_sixteen_publications(tmp_path: Path) -> None:
    _result, requests = drive(tmp_path, "queue", STUB_DELAY_MS="20")

    statuses = [request for request in requests if request["kind"] == "status"]
    assert [request["sequence"] for request in statuses] == list(range(1, 17))
    assert [request["status"] for request in statuses] == ["busy", "idle"] * 8


def test_at_most_eight_helpers_run_at_once(tmp_path: Path) -> None:
    _result, requests = drive(tmp_path, "helpers", STUB_DELAY_MS="500")

    assert kinds(requests).count("status") == 8
