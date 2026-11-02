// Metadata-only hook wrapper for the Codex 678 run. Reads the hook payload
// from stdin, hands the same bytes to Dashpot's real Codex publisher, passes
// the publisher's stdout back to Codex, and posts the payload's identity
// fields, this process's ancestry up to the runner, the terminal marker it
// inherited, and the publisher's exit status to the runner's sink.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type", "permission_mode", "model"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const startedAt = Date.now();
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 8000 });
if (published.stdout) process.stdout.write(published.stdout);
const record = {
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  terminal: process.env.SPIKE_TERMINAL ?? null,
  pid: process.pid,
  ancestry: ancestry(process.ppid, 6),
  publisher: { status: published.status, signal: published.signal, ms: Date.now() - startedAt,
    stderr: (published.stderr ?? "").slice(0, 400), error: published.error ? String(published.error) : null },
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
// Codex sees the publisher's own exit status, as with an installed hook.
process.exitCode = published.status ?? 1;
