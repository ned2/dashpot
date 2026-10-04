// Metadata-only hook wrapper for the Codex 460 standalone-resume run. Reads
// the hook payload from stdin and, for an event `dashpot integrate codex`
// subscribes, hands the same bytes to the Dashpot publisher the runner names
// in `$SPIKE_ROOT/publisher` for the current scenario, and passes its stdout
// back to Codex. It then posts the payload's identity fields, this process's
// ancestry, the publisher's exit status, and the session's stored hook record
// as Dashpot left it, to the runner's sink.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, tool inputs and responses stay out of the trace.
const retained = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "trigger", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active", "model"];
const subscribed = new Set((process.env.SPIKE_SUBSCRIBED ?? "").split(","));
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const startedAt = Date.now();
// The runner switches publishers between scenarios; a daemon's environment
// is fixed when it starts, so the choice is read per hook.
const [publisherName, publisherPath] = readFileSync(path.join(process.env.SPIKE_ROOT, "publisher"), "utf8").trim().split("\t");
let publisher = null;
if (subscribed.has(payload.hook_event_name)) {
  const published = spawnSync(publisherPath, [], { input: raw, encoding: "utf8", timeout: 8000 });
  if (published.stdout) process.stdout.write(published.stdout);
  // The publisher prints only a continuation notice and reports failures on
  // stderr; both are Dashpot's own text, never the session's.
  publisher = { name: publisherName, status: published.status, signal: published.signal, ms: Date.now() - startedAt,
    stdout: (published.stdout ?? "").slice(0, 400), stderr: (published.stderr ?? "").slice(0, 400), error: published.error ? String(published.error) : null };
}
// The session's record in the fixture's project store, read right after this
// hook's own write; a concurrent hook may already have replaced it.
const storedRecord = (sessionId) => {
  if (typeof sessionId !== "string") return null;
  // Dashpot keys a Codex record by its native session id, or by the scoped
  // key when another harness claims that id.
  const keys = [sessionId, `codex-session-${createHash("sha256").update(sessionId).digest("hex")}`];
  let record;
  for (const key of keys) {
    try { record = JSON.parse(readFileSync(path.join(process.env.SPIKE_SESSIONS_DIR, `${key}.json`), "utf8")); break; } catch {}
  }
  if (!record) return { missing: true };
  return { event: record.event ?? null, source: record.source ?? null, state: record.state ?? null,
    liveSubagents: record.liveSubagents ?? null, subagentProcesses: record.subagentProcesses ?? null,
    sessionProcess: record.sessionProcess ? { pid: record.sessionProcess.pid, startedAt: record.sessionProcess.startedAt } : null };
};
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CODEX"))),
  pid: process.pid,
  ancestry: ancestry(process.ppid),
  publisher,
  stored: storedRecord(payload.session_id),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(2500) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
// Codex sees the publisher's own exit status, as with an installed hook.
process.exitCode = publisher ? publisher.status ?? 1 : 0;
