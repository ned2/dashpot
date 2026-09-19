// Metadata-only hook publisher for the Codex 269 experiment. Reads the hook
// payload from stdin and posts its identity fields, the CODEX_* environment,
// and this process's ancestry to the runner's sink.
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "tool_use_id", "permission_mode", "stop_hook_active", "model", "trigger"];
let payload = {};
try { payload = JSON.parse(readFileSync(0, "utf8") || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  // transcript_path names a file under the fixture; only its presence is retained.
  hasTranscriptPath: typeof payload.transcript_path === "string",
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: ancestry(process.ppid),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook publish failed: ${error}\n`);
}
