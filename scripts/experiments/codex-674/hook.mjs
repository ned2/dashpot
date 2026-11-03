// Metadata-only hook wrapper for the Codex 674 follow-up hook run. Reads the
// hook payload from stdin and posts its identity fields to the runner's
// sink, tagged with the subscription that ran it (`node hook.mjs <tag>`).
// A lifecycle event Dashpot subscribes is also handed, byte for byte, to
// Dashpot's real Codex publisher, whose stdout and exit status Codex sees as
// with an installed hook. `PreToolUse` and `PostToolUse` are recorded only.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

const tag = process.argv[2] ?? "untagged";
// Prompts, messages, transcripts and command lines stay out of the trace:
// of a payload, only these fields' values are kept, and of a tool's input or
// response, only the values of the identity fields below.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "tool_use_id", "permission_mode", "stop_hook_active", "model"];
const identity = ["target", "id", "agent_id", "task_name", "agent_path", "nickname", "fork_turns", "interrupt", "agent_type", "targets", "timeout_ms"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
// The shape of a value: its type, and for an object its keys and the values
// of its identity fields; for a string, its length and whether it is JSON.
const shape = (value) => {
  if (value === undefined) return undefined;
  if (value === null) return { type: "null" };
  if (Array.isArray(value)) return { type: "array", length: value.length };
  if (typeof value === "object") {
    return { type: "object", keys: Object.keys(value),
      identity: Object.fromEntries(identity.filter((key) => key in value).map((key) => [key, value[key]])) };
  }
  if (typeof value === "string") {
    let parsed = null;
    try { parsed = JSON.parse(value); } catch {}
    return { type: "string", length: value.length, json: parsed !== null && typeof parsed === "object" ? shape(parsed) : null };
  }
  return { type: typeof value, value };
};
const tool = "tool_name" in payload;
let published = null;
const startedAt = Date.now();
if (tag === "lifecycle") {
  const ran = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 8000 });
  if (ran.stdout) process.stdout.write(ran.stdout);
  // The publisher prints only a continuation notice and reports failures on
  // stderr; both are Dashpot's own text, never the session's.
  published = { status: ran.status, signal: ran.signal, ms: Date.now() - startedAt,
    stderr: (ran.stderr ?? "").slice(0, 400), error: ran.error ? String(ran.error) : null };
  process.exitCode = ran.status ?? 1;
}
const record = {
  tag,
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  toolInput: tool ? shape(payload.tool_input) : undefined,
  toolResponse: tool ? shape(payload.tool_response) : undefined,
  // A hook names its thread's transcript, and `SubagentStop` the worker's
  // too; the runner reads only each transcript's session metadata.
  transcriptPath: payload.transcript_path ?? null,
  agentTranscriptPath: payload.agent_transcript_path ?? null,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX_"))),
  pid: process.pid,
  ancestry: ancestry(process.ppid).slice(0, 4).map((entry) => ({ pid: entry.pid, comm: entry.comm })),
  publisher: published,
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
