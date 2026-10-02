// Metadata-only hook wrapper for the Codex 356 acceptance run. Reads the hook
// payload from stdin, hands the same bytes to Dashpot's real Codex publisher,
// passes the publisher's stdout back to Codex, and posts the payload's
// identity fields, this process's ancestry, and the publisher's exit status
// to the runner's sink. For a timing scenario, the mode file the runner
// writes can also make a SessionEnd hook start a detached waiter that watches
// the hook's Codex host, then hold, posting a beat every 500 ms, so the trace
// shows when Codex kills the hook and when its host exits.
import { spawn, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active", "model"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
let mode = {};
try { mode = JSON.parse(readFileSync(process.env.SPIKE_MODE_FILE, "utf8")); } catch {}
const startedAt = Date.now();
const chain = ancestry(process.ppid);
const host = chain.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 8000 });
if (published.stdout) process.stdout.write(published.stdout);
const post = (body) => fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(2500) })
  .catch((error) => process.stderr.write(`hook trace failed: ${error}\n`));
await post({
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  cwd: process.cwd(),
  pid: process.pid,
  host,
  startedAt,
  ancestry: chain,
  // The publisher prints only a continuation notice and reports failures on
  // stderr; both are Dashpot's own text, never the session's.
  publisher: { status: published.status, signal: published.signal, ms: Date.now() - startedAt,
    stdout: (published.stdout ?? "").slice(0, 400), stderr: (published.stderr ?? "").slice(0, 400), error: published.error ? String(published.error) : null },
});
if (payload.hook_event_name === "SessionEnd") {
  const hold = mode.sessionEndHoldMs ?? 0;
  if (mode.watchHost && host !== null) {
    const waiter = spawn(process.execPath, [new URL("./waiter.mjs", import.meta.url).pathname, String(host), String(startedAt), payload.session_id ?? ""],
      { detached: true, stdio: "ignore", env: process.env });
    waiter.unref();
  }
  while (Date.now() - startedAt < hold) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await post({ kind: "hook.beat", session: payload.session_id, pid: process.pid, host, sinceBegin: Date.now() - startedAt });
  }
  await post({ kind: "hook.end", session: payload.session_id, pid: process.pid, host, sinceBegin: Date.now() - startedAt });
}
// Codex sees the publisher's own exit status, as with an installed hook.
process.exitCode = published.status ?? 1;
