// Metadata-only hook for the Codex 666 fresh-Worker tools and lineage run.
// Reads the hook payload from stdin and posts its identity fields, the
// CODEX_* environment and this process's ancestry to the runner's sink. It
// publishes nothing anywhere else and prints nothing, so Codex carries on as
// with no hook at all.
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "source", "reason", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active", "model"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX_") && key !== "CODEX_HOME")),
  pid: process.pid,
  ancestry: ancestry(process.ppid),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
