// Hook command for the Claude Code 162 acceptance run: hands the hook input
// to Dashpot's real Claude Code publisher, then posts the input's identity
// and location fields, the CLAUDE_* environment, this process's ancestry,
// and the publisher's exit status and output to the runner's sink. The
// publisher's output is passed on to Claude Code unchanged.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts and tool responses stay out of the trace. The worktree
// tools' inputs are kept: they say where the session was asked to go.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "tool_use_id", "permission_mode", "stop_hook_active"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const input = payload.tool_input ?? {};
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 20000 });
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  toolInput: payload.tool_input === undefined ? undefined : { keys: Object.keys(input), path: input.path, name: input.name, action: input.action },
  publisher: { status: published.status, signal: published.signal, stdout: published.stdout?.slice(0, 2000), stderr: published.stderr?.slice(-2000) },
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CLAUDE") && key !== "CLAUDE_CODE_MESSAGING_TOKEN")),
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: ancestry(process.ppid),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(5000) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
if (published.stdout) process.stdout.write(published.stdout);
process.exitCode = published.status ?? 1;
