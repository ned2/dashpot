// Hook command for the Claude Code 479 run. For an event `dashpot integrate
// claude-code` subscribes, it hands the hook input to Dashpot's real Claude
// Code publisher (SPIKE_PUBLISHER) and passes its output on unchanged; with
// `--trace-only` (the extra events the run watches, such as Notification and
// PermissionRequest) it publishes nothing. Either way it posts the input's
// identity and lifecycle fields, the Lead-link probe variables, this
// process's ancestry and the publisher's exit status to the runner's sink.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

const traceOnly = process.argv.includes("--trace-only");
// Prompts, transcripts and tool inputs stay out of the trace. A Notification's
// message and a messaging tool's response are the harness's own text.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active", "notification_type"];
const probeEnv = (key) => (key.startsWith("CLAUDE") && key !== "CLAUDE_CODE_MESSAGING_TOKEN") || key.startsWith("DASHPOT_LEAD") || key.startsWith("DASHPOT_479_") || key === "SPIKE_STAMP";
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const published = traceOnly ? null : spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 20000 });
const text = (value) => value === undefined ? undefined : (typeof value === "string" ? value : JSON.stringify(value)).slice(0, 600);
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  traceOnly,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  // A Stop's final message is the Worker's hand-back; only its presence and length are kept.
  lastAssistantMessage: "last_assistant_message" in payload
    ? { type: typeof payload.last_assistant_message, length: typeof payload.last_assistant_message === "string" ? payload.last_assistant_message.length : null } : undefined,
  notification: payload.hook_event_name === "Notification" ? text(payload.message) : undefined,
  // A submitted prompt keeps only the fixture's `SPIKE:` labels, its framing
  // tag names and its length, so a message queued mid-turn can be followed.
  prompt: typeof payload.prompt === "string" ? { labels: [...payload.prompt.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]),
    tags: [...new Set([...payload.prompt.matchAll(/<([a-z][a-z0-9_-]*)[\s>]/g)].map((match) => match[1]))], length: payload.prompt.length } : undefined,
  toolResponse: payload.hook_event_name === "PostToolUse" && ["SendMessage", "ListAgents"].includes(payload.tool_name) ? text(payload.tool_response) : undefined,
  toolInputKeys: payload.tool_input === undefined ? undefined : Object.keys(payload.tool_input),
  toolTarget: payload.tool_name === "SendMessage" ? { to: payload.tool_input?.to, notifyWhenIdle: payload.tool_input?.notify_when_idle } : undefined,
  publisher: published === null ? null : published.status === 0 && !published.signal && !published.stdout && !published.stderr ? { status: 0 }
    : { status: published.status, signal: published.signal, stdout: published.stdout?.slice(0, 2000), stderr: published.stderr?.slice(-2000) },
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => probeEnv(key))),
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: ancestry(process.ppid),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(5000) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
if (published?.stdout) process.stdout.write(published.stdout);
process.exitCode = published ? published.status ?? 1 : 0;
