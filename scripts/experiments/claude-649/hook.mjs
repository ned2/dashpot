// Hook command for the Claude Code 649 goal-driven Lead run: hands the hook
// input to Dashpot's real Claude Code publisher, then posts the input's
// identity fields, the size of its background task list, the CLAUDE_*
// environment, this process's ancestry, and the publisher's exit status and
// output to the runner's sink. The publisher's output is passed on to Claude
// Code unchanged.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, assistant messages and tool responses stay out of
// the trace.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 8000 });
const tasks = Array.isArray(payload.background_tasks) ? payload.background_tasks : null;
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  backgroundTasks: tasks && { count: tasks.length, keys: [...new Set(tasks.flatMap((task) => Object.keys(task ?? {})))].sort(),
    types: tasks.map((task) => task?.type ?? task?.kind ?? null), statuses: tasks.map((task) => task?.status ?? null) },
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
