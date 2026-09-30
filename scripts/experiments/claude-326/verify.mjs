// Independent verifier for the Claude Code 326 trace. It imports nothing from
// the runner or from Dashpot and checks the recorded `ps` evidence against the
// claims the experiment document makes about supervised process shapes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace path");
const expectedVersion = process.argv[3] ?? "2.1.285";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const environment = of("environment")[0];
assert.equal(environment.version, `${expectedVersion} (Claude Code)`);

const escaped = expectedVersion.replaceAll(".", "\\.");
// The shapes the experiment document names. A worker is spawned directly with
// its session, resumed from its transcript, or claimed from a pre-warmed spare.
const shapes = {
  "worker-direct": new RegExp(`^\\S*/claude/versions/${escaped} --session-id ([0-9a-f-]{36}) `),
  "worker-resumed": new RegExp(`^\\S*/claude/versions/${escaped} --resume (\\S+) `),
  "worker-spare": /^claude bg-spare --bg-spare \S+\/spare\/[0-9a-f]+\.claim\.sock$/,
  supervisor: new RegExp(`^\\S*/claude/versions/${escaped} daemon run `),
  "pty-host": /^claude bg-pty-host --bg-pty-host \S+\.sock \d+ \d+ -- (.*)$/,
};
const shapeOf = (args) => Object.keys(shapes).find((name) => shapes[name].test(args ?? "")) ?? "unclassified";

// 1. Every process a hook or shell names by CLAUDE_PID is a worker, named by
//    version in `comm`, in one of the three worker shapes.
const harness = of("probe.harness");
assert(harness.length >= 3, "at least three harness processes probed");
const sessionsByPid = new Map();
for (const record of of("hook")) {
  const pid = Number(record.env.CLAUDE_PID);
  if (!sessionsByPid.has(pid)) sessionsByPid.set(pid, new Set());
  sessionsByPid.get(pid).add(record.payload.session_id);
}
const harnessShapes = {};
for (const probe of harness) {
  assert(probe.present, `harness process ${probe.pid} was present when probed`);
  assert.equal(probe.comm, expectedVersion, `harness process ${probe.pid} comm`);
  const shape = shapeOf(probe.args);
  assert(shape.startsWith("worker-"), `harness process ${probe.pid} is a worker shape, not ${shape}: ${probe.args}`);
  harnessShapes[shape] = (harnessShapes[shape] ?? 0) + 1;
  // 2. Each worker process hosts exactly one Agent Session Identity.
  const sessions = [...(sessionsByPid.get(probe.pid) ?? [])];
  assert.equal(sessions.length, 1, `worker ${probe.pid} hosts one session: ${sessions}`);
  // 3. A direct worker's argv names its session; a resumed one, its transcript.
  const match = probe.args.match(shapes[shape]);
  if (shape === "worker-direct") assert.equal(match[1], sessions[0]);
  if (shape === "worker-resumed") assert(match[1].endsWith(`/${sessions[0]}.jsonl`), `resumed transcript names ${sessions[0]}`);
}
assert(harnessShapes["worker-direct"] >= 1, "a directly spawned worker was measured");
assert(harnessShapes["worker-spare"] >= 1, "a worker claimed from a spare was measured");

// 4. Every supervised process is named by version and has one of the named
//    shapes; the worker shells and commands below them are not supervised
//    processes. The supervisor and PTY hosts are never the process a hook or
//    shell names, and a PTY host's argv carries its child's whole command
//    after `--`, so a worker marker found anywhere in argv is not evidence.
const harnessPids = new Set(harness.map((probe) => probe.pid));
const snapshotShapes = {};
let ptyHostsNamingASession = 0;
for (const snapshot of of("probe.snapshot")) {
  for (const probe of snapshot.processes) {
    const shape = shapeOf(probe.args);
    if (shape === "unclassified") {
      assert.notEqual(probe.comm, expectedVersion, `version-named process ${probe.pid} has a named shape: ${probe.args}`);
      continue;
    }
    assert.equal(probe.comm, expectedVersion, `supervised process ${probe.pid} comm`);
    snapshotShapes[shape] = (snapshotShapes[shape] ?? 0) + 1;
    if (shape === "supervisor" || shape === "pty-host") assert(!harnessPids.has(probe.pid), `${shape} ${probe.pid} is never a CLAUDE_PID`);
    if (shape === "pty-host" && / --(session-id|resume) /.test(probe.args.match(shapes["pty-host"])[1])) ptyHostsNamingASession += 1;
  }
}
assert(snapshotShapes.supervisor >= 1 && snapshotShapes["pty-host"] >= 1, "supervisor and PTY hosts observed");
assert(ptyHostsNamingASession >= 1, "a PTY host's argv names its worker's session flag");

// 5. The abruptly killed worker comes back under the same session from a new
//    pid, and a respawned worker likewise; report which shape each took.
const kill = of("action.kill")[0];
const killedSession = [...sessionsByPid.get(kill.pid)][0];
const restart = of("hook").find((record) => record.receipt > kill.receipt && record.event === "SessionStart" && record.payload.session_id === killedSession);
assert(restart && restart.payload.source === "resume" && Number(restart.env.CLAUDE_PID) !== kill.pid, "killed worker resumed from a new pid");
const restartShape = shapeOf(harness.find((probe) => probe.pid === Number(restart.env.CLAUDE_PID)).args);
const respawn = of("worker.respawn")[0];
const respawnStart = of("hook").find((record) => record.receipt > respawn.receipt && record.event === "SessionStart");
assert.equal(respawnStart.payload.source, "resume");
const respawnShape = shapeOf(harness.find((probe) => probe.pid === Number(respawnStart.env.CLAUDE_PID)).args);

// 6. Nothing of the fixture outlived the run.
assert.deepEqual(of("cleanup.remaining").at(-1).pids, [], "no fixture process remains");

console.log(JSON.stringify({ version: expectedVersion, harnessShapes, snapshotShapes, ptyHostsNamingASession, restartAfterKill: restartShape, respawn: respawnShape }, null, 2));
console.log("All trace claims verified.");
