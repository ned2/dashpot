// Metadata-only hook wrapper for the Codex 466 run. It reads the hook payload
// from stdin, hands the same bytes to Dashpot's real Codex publisher, passes
// the publisher's stdout back to Codex, and posts the payload's identity
// fields, this process's ancestry and the publisher's exit status to the
// runner's sink.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type", "tool_name", "stop_hook_active"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const prompt = typeof payload.prompt === "string" ? payload.prompt : null;
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 8000 });
if (published.stdout) process.stdout.write(published.stdout);
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  labels: prompt === null ? undefined : [...prompt.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  pid: process.pid,
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm })),
  // The publisher prints only a continuation notice and reports failures on
  // stderr; both are Dashpot's own text, never the session's.
  publisher: { status: published.status, signal: published.signal, stdout: (published.stdout ?? "").slice(0, 400), stderr: (published.stderr ?? "").slice(0, 400) },
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
process.exitCode = published.status ?? 1;
