// Publish real Codex lifecycle hooks and retain their identity for Issue #665.
// Fixture prompts and transcript bytes are intentionally omitted.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

const raw = readFileSync(0, "utf8");
const payload = JSON.parse(raw);
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 10000 });
if (published.stdout) process.stdout.write(published.stdout);
const keys = ["session_id", "turn_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type"];
await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", signal: AbortSignal.timeout(3000), body: JSON.stringify({
  event: payload.hook_event_name,
  payload: Object.fromEntries(keys.filter((key) => key in payload).map((key) => [key, payload[key]])),
  publisher: { status: published.status, signal: published.signal, stderr: published.stderr },
  ancestry: ancestry(process.ppid),
}) });
process.exitCode = published.status ?? 1;
