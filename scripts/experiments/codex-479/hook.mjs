// Metadata-only hook wrapper for the Codex 479 run. It reads the hook payload
// from stdin, hands the same bytes to Dashpot's real Codex publisher, passes
// the publisher's stdout back to Codex, and posts the payload's identity
// fields, the fixture markers of a prompt, the CODEX_* and DASHPOT_*
// environment, this process's ancestry and the publisher's exit status to
// the runner's sink.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type", "tool_name", "permission_mode",
  "stop_hook_active", "model"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const prompt = typeof payload.prompt === "string" ? payload.prompt : null;
const startedAt = Date.now();
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 8000 });
if (published.stdout) process.stdout.write(published.stdout);
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  // Only the fixture's own markers of a prompt.
  markers: prompt === null ? undefined : [...prompt.matchAll(/(SPIKE|NOTE):([a-z0-9_-]+)/g)].map((match) => match[0]),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX") || key.startsWith("DASHPOT"))),
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm, cmdline, cwd }) => ({ pid, ppid, comm, cmdline: cmdline.slice(0, 160), cwd })),
  // The publisher prints only a continuation notice and reports failures on
  // stderr; both are Dashpot's own text, never the session's.
  publisher: { status: published.status, signal: published.signal, ms: Date.now() - startedAt,
    stdout: (published.stdout ?? "").slice(0, 400), stderr: (published.stderr ?? "").slice(0, 400), error: published.error ? String(published.error) : null },
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
// Codex sees the publisher's own exit status, as with an installed hook.
process.exitCode = published.status ?? 1;
