// Replay late, deleted, forged and misplaced publications through Dashpot's
// installed OpenCode helper, from a shell command OpenCode runs, so the
// helper finds the real server above it. OpenCode cannot be made to deliver
// a late or repeated event on demand; this sends the helper the requests such
// a delivery would, for one idle session whose Publisher Record entry it
// reads, and reports each acknowledgment with that session's hook record and
// entry before and after.
//
// Usage: node replay.mjs <idle session> <deleted session> <deleted session's location> <location outside every Project>
import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const [target, deleted, deletedLocation, outside] = process.argv.slice(2);
const pid = Number(process.env.DASHPOT_OPENCODE_PID);
const location = process.cwd();
const store = path.join(location, ".dashpot", "state", "sessions");
const entry = () => JSON.parse(readFileSync(path.join(store, "opencode", "publisher.json"), "utf8")).sessions[target];
const hookRecord = () => {
  const { state, event, lastActivityAt, sessionProcess, sessionProcessUnobservable } = JSON.parse(readFileSync(path.join(store, `${target}.json`), "utf8"));
  return { state, event, lastActivityAt, pid: sessionProcess?.pid ?? null, unobservable: sessionProcessUnobservable ?? null };
};
const generation = randomUUID();
const send = (label, fields, claimed = pid) => {
  const request = { protocol: 2, generation, pid: claimed, deadlineMs: 3000, ...fields };
  const result = spawnSync(process.env.SPIKE_HELPER, [], { input: JSON.stringify(request), encoding: "utf8", timeout: 10000 });
  let acknowledgment = null;
  try { acknowledgment = JSON.parse(result.stdout.trim().split("\n").pop()); } catch {}
  return { label, status: result.status, acknowledgment };
};
const event = (session, root, at, type, sequence) => ({ kind: "event", session: { id: session, root, location: at },
  event: { id: `evt_replay_${randomUUID()}`, type, sequence } });
const before = { record: hookRecord(), entry: entry() };
const outcomes = [
  send("register", { kind: "register", location }),
  send("late-end", event(target, target, location, "session.execution.succeeded", before.entry.sequence)),
  send("earlier-start", event(target, target, location, "session.execution.started", 0)),
  send("deleted-session", event(deleted, deleted, deletedLocation, "session.execution.started", 1000000)),
  send("outside-project", event(target, target, outside, "session.execution.started", before.entry.sequence + 1)),
  send("forged-host", event(target, target, location, "session.execution.started", before.entry.sequence + 1), process.pid),
];
const after = { record: hookRecord(), entry: entry() };
await fetch(process.env.SPIKE_SINK + "/replay", { method: "POST", body: JSON.stringify({ target, before, after, outcomes }),
  signal: AbortSignal.timeout(3000) }).catch(() => {});
console.log(JSON.stringify(outcomes.map((outcome) => [outcome.label, outcome.acknowledgment?.result])));
