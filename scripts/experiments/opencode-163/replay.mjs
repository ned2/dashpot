// Replay late and duplicate publications through Dashpot's installed OpenCode
// helper, from a shell command OpenCode runs, so the helper finds the real
// backend above it. OpenCode cannot be made to deliver a late or repeated
// publication on demand; this sends the helper the requests such a delivery
// would, for one idle session it reads the watermark of, and reports each
// acknowledgment with the session's hook record before and after.
//
// Usage: node replay.mjs <idle session> <retired generation> <deleted session>
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const [target, retired, deleted] = process.argv.slice(2);
const generation = process.env.DASHPOT_OPENCODE_GENERATION;
const pid = Number(process.env.DASHPOT_OPENCODE_PID);
const directory = process.cwd();
const store = path.join(directory, ".dashpot", "state", "sessions");
const publisher = readdirSync(path.join(store, "opencode")).filter((name) => name.endsWith(".json"))
  .map((name) => JSON.parse(readFileSync(path.join(store, "opencode", name), "utf8")))
  .find((record) => record.backend.pid === pid && record.directory === directory);
const watermark = publisher.sessions[target];
const hookRecord = () => {
  const { state, event, lastActivityAt, sessionProcess } = JSON.parse(readFileSync(path.join(store, `${target}.json`), "utf8"));
  return { state, event, lastActivityAt, pid: sessionProcess?.pid ?? null };
};
const send = (label, fields, claimed = pid) => {
  const request = { protocol: 1, generation, directory, pid: claimed, deadlineMs: 3000, ...fields };
  const result = spawnSync(process.env.SPIKE_HELPER, [], { input: JSON.stringify(request), encoding: "utf8", timeout: 10000 });
  let acknowledgment = null;
  try { acknowledgment = JSON.parse(result.stdout.trim().split("\n").pop()); } catch {}
  return { label, status: result.status, acknowledgment };
};
const session = (id) => ({ id, directory, parentID: null });
const before = hookRecord();
const outcomes = [
  send("register-again", { kind: "register" }),
  send("stale-status", { kind: "status", status: watermark.status, sequence: watermark.sequence, session: session(target), root: target }),
  send("duplicate-status", { kind: "status", status: watermark.status, sequence: watermark.sequence + 1, session: session(target), root: target }),
  send("retired-generation", { kind: "status", status: "busy", sequence: watermark.sequence + 2, session: session(target), root: target, generation: retired }),
  send("deleted-session", { kind: "status", status: "busy", sequence: 1000000, session: session(deleted), root: deleted }),
  send("forged-backend", { kind: "register" }, process.pid),
];
const after = hookRecord();
await fetch(process.env.SPIKE_SINK + "/replay", { method: "POST", body: JSON.stringify({ target, watermark, before, after, outcomes }),
  signal: AbortSignal.timeout(3000) }).catch(() => {});
console.log(JSON.stringify(outcomes.map((outcome) => [outcome.label, outcome.acknowledgment?.result])));
